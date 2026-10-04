"""Private PDF storage; provider credentials never leave the server."""
import io
from urllib.parse import quote, urlparse
import requests
from django.conf import settings
from django.core.files.base import File
from django.core.files.storage import Storage

MAX_PDF_BYTES = 5 * 1024 * 1024

class StorageUnavailable(ValueError):
    pass


def storage_request(method, path, **kwargs):
    try:
        response = requests.request(method, settings.SUPABASE_URL + '/storage/v1/' + path,
        headers={'Authorization': 'Bearer ' + settings.SUPABASE_SERVICE_ROLE_KEY,
                 'apikey': settings.SUPABASE_SERVICE_ROLE_KEY, **kwargs.pop('headers', {})},
        timeout=(5, 20), allow_redirects=False, **kwargs)
    except requests.RequestException:
        raise StorageUnavailable('Private storage is unreachable. Please retry.')
    if not 200 <= response.status_code < 300:
        response.close()
        raise StorageUnavailable(f'Private storage request failed (HTTP {response.status_code}). Please retry.')
    return response


def object_path(name):
    if not name.startswith('resumes/') or '..' in name or '\\' in name:
        raise StorageUnavailable('Invalid résumé object path.')
    return quote(settings.SUPABASE_STORAGE_BUCKET, safe='') + '/' + quote(name, safe='/')


def signed_url(name, upload=False):
    path = 'object/upload/sign/' if upload else 'object/sign/'
    with storage_request('POST', path + object_path(name), json={'expiresIn': 300, 'upsert': False}) as response:
        try:
            data = response.json()
        except ValueError:
            raise StorageUnavailable('Private storage returned an unexpected response. Check the project API URL.')
    value = data.get('signedURL') or data.get('signedUrl') or data.get('url')
    if not value:
        raise StorageUnavailable('Private storage did not return a signed URL.')
    if not value.startswith('https://'):
        value = settings.SUPABASE_URL + ('/storage/v1' if not value.startswith('/storage/v1/') else '') + value
    if urlparse(value).netloc != urlparse(settings.SUPABASE_URL).netloc:
        raise StorageUnavailable('Private storage returned an unexpected URL.')
    return value


def download_pdf(name):
    with storage_request('GET', 'object/' + object_path(name), stream=True) as response:
        content = bytearray()
        for chunk in response.iter_content(65536):
            content.extend(chunk)
            if len(content) > MAX_PDF_BYTES:
                raise StorageUnavailable('PDF exceeds 5 MB.')
    return bytes(content)


class SupabaseStorage(Storage):
    def _open(self, name, mode='rb'):
        return File(io.BytesIO(download_pdf(name)), name=name)

    def _save(self, name, content):
        body = content.read(MAX_PDF_BYTES + 1)
        if len(body) > MAX_PDF_BYTES:
            raise StorageUnavailable('PDF exceeds 5 MB.')
        with storage_request('POST', 'object/' + object_path(name), data=body,
                             headers={'Content-Type': 'application/pdf', 'x-upsert': 'false'}):
            pass
        return name

    def exists(self, name):
        # Generated UUID keys and x-upsert=false prevent overwriting objects.
        return False

    def url(self, name):
        return signed_url(name)

    def delete(self, name):
        with storage_request('DELETE', 'object/' + quote(settings.SUPABASE_STORAGE_BUCKET, safe=''), json={'prefixes': [name]}):
            pass
