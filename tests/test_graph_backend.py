from unittest import mock

from django.core.mail import EmailMultiAlternatives

from notifications import graph_backend


def test_graph_backend_posts_html(settings):
    settings.GRAPH_SENDER_MAILBOX = "servicehours@school.test"
    msg = EmailMultiAlternatives(
        "Hi", "plain", "servicehours@school.test", ["sup@org.test"], reply_to=["kid@school.test"]
    )
    msg.attach_alternative("<p>html</p>", "text/html")
    with (
        mock.patch.object(graph_backend, "_token", return_value="tok"),
        mock.patch.object(graph_backend.requests, "post") as post,
    ):
        post.return_value.status_code = 202
        sent = graph_backend.GraphEmailBackend().send_messages([msg])
    assert sent == 1
    url = post.call_args.args[0]
    body = post.call_args.kwargs["json"]["message"]
    assert url.endswith("/users/servicehours@school.test/sendMail")
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"
    assert body["body"] == {"contentType": "HTML", "content": "<p>html</p>"}
    assert body["toRecipients"][0]["emailAddress"]["address"] == "sup@org.test"
    assert body["replyTo"][0]["emailAddress"]["address"] == "kid@school.test"


def test_graph_failure_does_not_lose_entry(
    student9, make_entry, settings, django_capture_on_commit_callbacks
):
    settings.EMAIL_BACKEND = "notifications.graph_backend.GraphEmailBackend"
    with mock.patch.object(graph_backend, "_token", side_effect=RuntimeError("down")):
        with django_capture_on_commit_callbacks(execute=True):
            entry = make_entry(student9)
    assert entry.pk and entry.status == "pending"
