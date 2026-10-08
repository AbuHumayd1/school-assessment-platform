"""Separate platform surface over the shared content/workflow engine."""
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers, viewsets
from rest_framework.exceptions import ValidationError

from audit.services import record_event
from institutions.platform_views import PlatformPermission, PlatformPagination
from subjects.models import Subject
from subjects.serializers import SubjectSerializer
from .models import Question, Topic
from .serializers import TopicSerializer
from .views import QuestionViewSet


class PlatformContentMixin:
    permission_classes = [PlatformPermission]
    pagination_class = PlatformPagination
    platform_library = True

    def get_permissions(self):
        # Includes collection actions and inherited workflow actions.
        return [PlatformPermission()]

    def get_serializer_context(self):
        # Bypass the institution mixin: platform actions never resolve a workspace.
        context = viewsets.GenericViewSet.get_serializer_context(self)
        context.update(platform_library=True, institution=None)
        return context

    def audit(self, instance, action):
        record_event(institution=None, actor=self.request.user, event_type='platform_content_changed',
                     resource=instance, metadata={'action': action})

    def perform_create(self, serializer):
        with transaction.atomic():
            try:
                instance = serializer.save(owner_scope='platform', institution=None)
            except ModelValidationError as error:
                raise ValidationError(error.message_dict if hasattr(error, 'message_dict') else error.messages)
            self.audit(instance, 'created')

    def perform_update(self, serializer):
        with transaction.atomic():
            try:
                instance = serializer.save()
            except ModelValidationError as error:
                raise ValidationError(error.message_dict if hasattr(error, 'message_dict') else error.messages)
            self.audit(instance, 'updated')


class PlatformSubjectSerializer(SubjectSerializer):
    class Meta(SubjectSerializer.Meta):
        validators = []

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if 'institution' in self.initial_data:
            raise serializers.ValidationError({'institution': 'Platform subjects have no institution.'})
        code = attrs.get('code', getattr(self.instance, 'code', None))
        duplicates = Subject.objects.filter(owner_scope='platform', code=code)
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError({'code': 'A platform subject with this code already exists.'})
        return attrs


class PlatformSubjectViewSet(PlatformContentMixin, viewsets.ModelViewSet):
    serializer_class = PlatformSubjectSerializer
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_queryset(self):
        return Subject.objects.filter(owner_scope='platform', institution__isnull=True).order_by('name', 'pk')

    def perform_create(self, serializer):
        try:
            super().perform_create(serializer)
        except IntegrityError:
            if Subject.objects.filter(owner_scope='platform', code=serializer.validated_data['code']).exists():
                raise ValidationError({'code': 'A platform subject with this code already exists.'})
            raise


class PlatformTopicViewSet(PlatformContentMixin, viewsets.ModelViewSet):
    serializer_class = TopicSerializer
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_queryset(self):
        queryset = Topic.objects.filter(owner_scope='platform', institution__isnull=True).select_related('subject', 'parent')
        subject = self.request.query_params.get('subject')
        if subject:
            try:
                subject = int(subject)
            except (ValueError, TypeError):
                raise ValidationError({'subject': 'Enter a valid identifier.'})
            queryset = queryset.filter(subject_id=subject)
        return queryset


class PlatformQuestionViewSet(PlatformContentMixin, QuestionViewSet):
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_write_institution(self):
        return None

    def get_content_queryset(self):
        return Question.objects.filter(owner_scope='platform', institution__isnull=True)

    def perform_create(self, serializer):
        # The shared QuestionSerializer assigns ownership from trusted context.
        with transaction.atomic():
            try:
                question = serializer.save()
            except ModelValidationError as error:
                raise ValidationError(error.message_dict if hasattr(error, 'message_dict') else error.messages)
            self.audit(question, 'created')

    # Intentionally hide the inherited CSV action; platform imports are deferred.
    def import_csv(self, request, *args, **kwargs):
        raise ValidationError('Platform imports are not available.')
