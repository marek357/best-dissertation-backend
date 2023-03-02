from django.core.mail import send_mail


def send_annotator_welcome_email(annotator, inviting_contributor, project):
    subject = f'[Annopedia] Invitation to contribute to {project.name}'
    message = f'''
        Hi {annotator.contributor.username}!\n\n
        You have been invited by {inviting_contributor.username} to contribute
        to the project {project.name}!\n
        Please click the link to annotate: https://annopedia.marekmasiak.tech/annotator/annotate?token={annotator.token}\n
        Good luck!\n\n
        Best regards,\n
        Annopedia Team
    '''
    email_from = 'annopedia@zohomail.eu'
    recipient_list = [annotator.contributor.email]
    # https://docs.djangoproject.com/en/4.1/topics/email/
    send_mail(subject, message, email_from, recipient_list)
