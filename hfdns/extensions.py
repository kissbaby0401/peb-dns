# -*- coding: utf-8 -*-

from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()

from flask_migrate import Migrate

from flask_mail import Mail
mail = Mail()

from flask_cache import Cache
cache = Cache()

from flask_admin import Admin
admin = Admin()

from flask_login import LoginManager
login_manager = LoginManager()


from flask_babel import Babel
babel = Babel()

from flask_debugtoolbar import DebugToolbarExtension
toolbar = DebugToolbarExtension()

from flask_assets import Environment
assets = Environment()

from redis import Redis
redis = Redis()
session_redis = Redis()