from django.db import models

class KnowledgeSystem(models.Model):
    student_id = models.CharField(max_length=20)  # 학생 ID
    knowledge_unit = models.CharField(max_length=100)  # 소단원 지식체계
    major_unit = models.CharField(max_length=100)  # 대단원
    lecture_code = models.CharField(max_length=50)  # 강의 코드
    lecture_name = models.CharField(max_length=200)  # 강의명
    is_correct = models.BooleanField()  # 정오답 여부 (0, 1)

    created_at = models.DateTimeField(auto_now_add=True)  # 데이터 입력 시 자동 생성 시간

    def __str__(self):
        return f'{self.student_id} - {self.knowledge_unit} - {"Correct" if self.is_correct else "Incorrect"}'

class Question(models.Model):
    question_text = models.CharField(max_length=255)
    correct_answer = models.CharField(max_length=255)

    def __str__(self):
        return self.question_text
