"""Single-workspace judge access for the public hackathon deployment."""
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.crypto import salted_hmac


def access_stamp():
    return salted_hmac('verity-workspace', settings.VERITY_JUDGE_PASSWORD).hexdigest()


class WorkspaceAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        public = request.path in ['/', '/health/', '/workspace-login/'] or request.path.startswith('/static/')
        if settings.VERITY_JUDGE_PASSWORD and not public and request.session.get('workspace_access') != access_stamp():
            if request.method != 'GET' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Please sign in to the recruiter workspace.'}, status=403)
            return redirect('workspace_login')
        response = self.get_response(request)
        if not public: response['Cache-Control'] = 'no-store'
        return response
