from decimal import Decimal


def grade_for_percentage(percentage):
    score = Decimal(percentage)
    for threshold, grade in ((Decimal("70"), "A"), (Decimal("60"), "B"), (Decimal("50"), "C"), (Decimal("45"), "D"), (Decimal("40"), "E")):
        if score >= threshold:
            return grade
    return "F"
