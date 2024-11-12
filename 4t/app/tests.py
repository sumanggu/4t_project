from django.test import TestCase
from .models import KnowledgeSystem

class KnowledgeSystemTest(TestCase):
    def setUp(self):
        KnowledgeSystem.objects.create(
            student_id="12345", 
            knowledge_unit="Unit1", 
            major_unit="Major1", 
            lecture_code="L001", 
            lecture_name="Lecture1", 
            is_correct=True
        )

    def test_knowledge_system_creation(self):
        knowledge = KnowledgeSystem.objects.get(student_id="12345")
        self.assertEqual(knowledge.knowledge_unit, "Unit1")
        self.assertTrue(knowledge.is_correct)
