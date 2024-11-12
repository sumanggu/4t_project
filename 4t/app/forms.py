from django import forms


class KnowledgeSystemForm(forms.Form):
    student_id = forms.CharField(label='학생 ID', max_length=100)
    knowledge_unit = forms.CharField(label='풀이할 단원', max_length=100)

class AnswerForm(forms.Form):
    answer = forms.CharField(max_length=255, label="Your Answer")
