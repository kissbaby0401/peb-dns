from flask import Flask, Blueprint, render_template, request, jsonify
from configs.config import config, config_pyfiles
import click
from flask_migrate import Migrate, MigrateCommand
from .extensions import mail, db, login_manager
from flask_babel import gettext as _
from .models import User, AnonymousUser
from .views.website import auth, dns, main
from .views.api_1_0 import api
import os

APP_NAME = 'HFDNS'

def configure_extensions(app):
    mail.init_app(app)
    db.init_app(app)
    migrate = Migrate(app, db)

    login_manager.session_protection = 'strong'
    login_manager.anonymous_user = AnonymousUser
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(id):
        return User.query.get(int(id))

    login_manager.init_app(app)
    login_manager.login_message = _('请先登陆后访问该页面.')
    login_manager.needs_refresh_message = _('请重新认证后访问.')


def configure_blueprints(app, blueprints):
    for blueprint in blueprints:
        app.register_blueprint(blueprint)


def configure_error_handlers(app):
    
    @app.errorhandler(403)
    def forbidden(e):
        if request.accept_mimetypes.accept_json and \
                not request.accept_mimetypes.accept_html:
            response = jsonify({'error': 'forbidden'})
            response.status_code = 403
            return response
        return render_template('403.html'), 403

    @app.errorhandler(404)
    def page_not_found(e):
        # print(request.accept_mimetypes.accept_json)
        # print(request.accept_mimetypes.accept_html)
        if request.accept_mimetypes.accept_json and \
                not request.accept_mimetypes.accept_html:
            response = jsonify({'error': 'not found'})
            response.status_code = 404
            return response
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        if request.accept_mimetypes.accept_json and \
                not request.accept_mimetypes.accept_html:
            response = jsonify({'error': 'internal server error'})
            response.status_code = 500
            return response
        return render_template('500.html'), 500


def create_app(config_name='default'):
    app = Flask(APP_NAME,
                static_folder='hfdns/static',
                template_folder='hfdns/templates')

    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    app.config.from_pyfile(config_pyfiles[config_name])
    app.config.from_pyfile('configs/dns_templates.cfg')
    configure_extensions(app)
    configure_blueprints(app, [auth, dns, main, api])
    configure_error_handlers(app)

    return app
