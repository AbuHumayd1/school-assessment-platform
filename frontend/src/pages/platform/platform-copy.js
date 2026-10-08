import { useLanguageMode } from '../../context/LanguageModeContext.jsx'

export const platformCopy = {
  'Platform Library': 'مكتبة المنصة', 'Institution Banks': 'بنوك المؤسسات',
  Overview: 'نظرة عامة', Clients: 'العملاء', Exams: 'الاختبارات', Reports: 'التقارير',
  Candidates: 'المرشحون', Submissions: 'التسليمات', Results: 'النتائج',
  'Platform Administrator': 'مدير المنصة', 'Return to Platform': 'العودة إلى المنصة',
  Managing: 'إدارة', 'Manage Client': 'إدارة العميل', 'Create Client': 'إنشاء عميل',
  'Search clients': 'البحث عن العملاء', Search: 'بحث', Client: 'العميل', Name: 'الاسم',
  Slug: 'معرّف الرابط', 'Institution Type': 'نوع المؤسسة', Timezone: 'المنطقة الزمنية',
  Workspace: 'مساحة العمل', 'Full Workspace': 'مساحة عمل كاملة', 'Managed Exam': 'اختبارات مُدارة',
  'Active Exams': 'الاختبارات النشطة', 'No clients found': 'لا يوجد عملاء',
  'Back to Clients': 'العودة إلى العملاء', Administrators: 'المديرون',
  'Add Administrator': 'إضافة مدير', Email: 'البريد الإلكتروني', 'Initial Password': 'كلمة المرور الأولية',
  'Required for new accounts only. Existing accounts keep their password.': 'مطلوبة للحسابات الجديدة فقط. تحتفظ الحسابات الحالية بكلمة المرور.',
  'Allow client administrators to release results to candidates': 'السماح لمديري العميل بنشر النتائج للمرشحين',
  On: 'مفعّل', Off: 'غير مفعّل', Save: 'حفظ', Cancel: 'إلغاء', Status: 'الحالة',
  Active: 'نشط', Inactive: 'غير نشط', 'No administrators yet': 'لم تتم إضافة مديرين بعد',
  'No exams found': 'لا توجد اختبارات', 'Open exam': 'فتح الاختبار',
  'Open client reports': 'فتح تقارير العميل',
  'Choose a client to view and download examination reports.': 'اختر عميلاً لعرض تقارير الاختبارات وتنزيلها.',
  'Examination operations': 'إدارة عمليات الاختبارات', 'Try again': 'إعادة المحاولة',
  'Something went wrong. Please try again.': 'حدث خطأ. يرجى المحاولة مرة أخرى.',
  'Administrator added': 'تمت إضافة المدير', 'Saved': 'تم الحفظ',
  'Loading…': 'جار التحميل…', 'We could not load this information.': 'تعذر تحميل هذه المعلومات.',
  Retry: 'إعادة المحاولة', Pagination: 'ترقيم الصفحات', Previous: 'السابق', Next: 'التالي', Page: 'الصفحة',
  draft: 'مسودة', review: 'قيد المراجعة', approved: 'معتمد', scheduled: 'مجدول', archived: 'مؤرشف',
  Questions: 'الأسئلة',
  School: 'مدرسة', 'Training Provider': 'جهة تدريب', Other: 'أخرى',
  'Scheduled Exams': 'الاختبارات المجدولة',
}

export function usePlatformCopy() {
  const { label, direction } = useLanguageMode()
  return { t: text => label(text, platformCopy[text] || text), direction }
}
