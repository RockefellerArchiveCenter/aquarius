DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'postgres',
        'USER': 'postgres',
        'HOST': 'aquarius-db',
        'PORT': 5432,
    }
}

ALLOWED_HOSTS = ['aquarius-web', 'localhost']

ARCHIVESSPACE = {
  "baseurl": "http://localhost:8089/",
  "username": "admin",
  "password": "admin",
  "repo_id": 2,
}

URSA_MAJOR = {
  "baseurl": "http://localhost:8005/",
}

AURORA = {
  "baseurl": "http://web:8000/api/",
  "username": "admin",
  "password": "password"
}

STATIC_ROOT = '/static'
