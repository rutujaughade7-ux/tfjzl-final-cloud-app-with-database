from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Choice, Course, Enrollment, Lesson, Question, Submission


class ExamFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('learner', password='pw12345', first_name='Rutuja')
        self.course = Course.objects.create(name='Python 101', description='Intro')
        lesson = Lesson.objects.create(title='Basics', order=0, course=self.course, content='x')

        # Q1 (2 pts): single correct answer, Q2 (3 pts): two correct answers
        self.q1 = Question.objects.create(lesson=lesson, question_text='2 + 2?', grade=2)
        self.q1_ok = Choice.objects.create(question=self.q1, choice_text='4', is_correct=True)
        self.q1_bad = Choice.objects.create(question=self.q1, choice_text='5', is_correct=False)

        self.q2 = Question.objects.create(lesson=lesson, question_text='Pick the primes', grade=3)
        self.q2_a = Choice.objects.create(question=self.q2, choice_text='2', is_correct=True)
        self.q2_b = Choice.objects.create(question=self.q2, choice_text='3', is_correct=True)
        self.q2_c = Choice.objects.create(question=self.q2, choice_text='4', is_correct=False)

        Enrollment.objects.create(user=self.user, course=self.course, mode='honor')
        self.client.login(username='learner', password='pw12345')

    def submit(self, *choices):
        data = {'choice_%d' % c.id: c.id for c in choices}
        return self.client.post(reverse('onlinecourse:submit', args=(self.course.id,)), data)

    def test_all_correct_passes(self):
        response = self.submit(self.q1_ok, self.q2_a, self.q2_b)
        submission = Submission.objects.get()
        self.assertRedirects(
            response,
            reverse('onlinecourse:show_exam_result', args=(self.course.id, submission.id)),
        )
        result = self.client.get(response['Location'])
        self.assertEqual(result.context['grade'], 100)
        self.assertEqual(result.context['total_score'], 5)
        self.assertContains(result, 'Congratulations')

    def test_wrong_answers_fail(self):
        response = self.submit(self.q1_bad, self.q2_c)
        result = self.client.get(response['Location'])
        self.assertEqual(result.context['grade'], 0)
        self.assertContains(result, 'Failed')
        self.assertContains(result, 'Re-test')

    def test_extra_wrong_choice_loses_the_question(self):
        response = self.submit(self.q1_ok, self.q2_a, self.q2_b, self.q2_c)
        result = self.client.get(response['Location'])
        self.assertEqual(result.context['total_score'], 2)  # only Q1
        self.assertEqual(result.context['grade'], 40)

    def test_partially_correct_multi_answer_loses_the_question(self):
        response = self.submit(self.q1_ok, self.q2_a)
        result = self.client.get(response['Location'])
        self.assertEqual(result.context['total_score'], 2)

    def test_choices_from_other_courses_are_ignored(self):
        other = Course.objects.create(name='Other', description='x')
        other_lesson = Lesson.objects.create(title='L', order=0, course=other, content='x')
        other_q = Question.objects.create(lesson=other_lesson, question_text='?', grade=1)
        foreign = Choice.objects.create(question=other_q, choice_text='y', is_correct=True)
        self.submit(self.q1_ok, foreign)
        self.assertEqual(Submission.objects.get().choices.count(), 1)

    def test_submit_requires_enrollment(self):
        Enrollment.objects.all().delete()
        response = self.submit(self.q1_ok)
        self.assertEqual(Submission.objects.count(), 0)
        self.assertRedirects(
            response, reverse('onlinecourse:course_details', args=(self.course.id,))
        )

    def test_result_of_wrong_course_is_404(self):
        self.submit(self.q1_ok)
        other = Course.objects.create(name='Other', description='x')
        url = reverse('onlinecourse:show_exam_result', args=(other.id, Submission.objects.get().id))
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_course_page_shows_exam_only_to_enrolled_learners(self):
        url = reverse('onlinecourse:course_details', args=(self.course.id,))
        self.assertContains(self.client.get(url), 'Start Exam')
        Enrollment.objects.all().delete()
        page = self.client.get(url)
        self.assertNotContains(page, 'Start Exam')
        self.assertContains(page, 'Enroll Now')
