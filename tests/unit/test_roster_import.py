import unittest

from app.database.roster_import import parse_roster_csv, export_roster_csv, RosterImportError


class TestRosterImport(unittest.TestCase):
    def test_basic_import(self):
        csv_text = "student_id,name,group\n1001,Ali Ahmadi,11A\n1002,Sara Mohammadi,11A\n"
        students, warnings = parse_roster_csv(csv_text)
        self.assertEqual(len(students), 2)
        self.assertEqual(students[0].student_id, "1001")
        self.assertEqual(students[0].name, "Ali Ahmadi")
        self.assertEqual(students[0].group, "11A")
        self.assertEqual(warnings, [])

    def test_missing_student_id_column_raises(self):
        with self.assertRaises(RosterImportError):
            parse_roster_csv("name,group\nAli,11A\n")

    def test_missing_student_id_value_is_skipped_not_fatal(self):
        csv_text = "student_id,name\n1001,Ali\n,NoID\n1003,Sara\n"
        students, warnings = parse_roster_csv(csv_text)
        self.assertEqual(len(students), 2)
        self.assertEqual(len(warnings), 1)
        self.assertIn("missing student_id", warnings[0])

    def test_duplicate_id_warns(self):
        csv_text = "student_id,name\n1001,Ali\n1001,Ali2\n"
        students, warnings = parse_roster_csv(csv_text)
        self.assertEqual(len(warnings), 1)
        self.assertIn("duplicate", warnings[0])

    def test_class_column_alias_accepted(self):
        csv_text = "student_id,name,class\n1001,Ali,11A\n"
        students, _ = parse_roster_csv(csv_text)
        self.assertEqual(students[0].group, "11A")

    def test_export_round_trips(self):
        csv_text = "student_id,name,group\n1001,Ali Ahmadi,11A\n"
        students, _ = parse_roster_csv(csv_text)
        exported = export_roster_csv(students)
        reimported, _ = parse_roster_csv(exported)
        self.assertEqual(reimported[0].student_id, "1001")
        self.assertEqual(reimported[0].name, "Ali Ahmadi")

    def test_empty_csv_raises(self):
        with self.assertRaises(RosterImportError):
            parse_roster_csv("")


if __name__ == "__main__":
    unittest.main()
