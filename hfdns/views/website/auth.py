from flask import Blueprint, request, jsonify, current_app, redirect, render_template, flash, url_for
from flask_login import login_user, logout_user, login_required, current_user
from . import auth
from hfdns.extensions import db
from hfdns.models import User
from hfdns.forms.auth import LoginForm
from ldap3 import Server, Connection, ALL


auth = Blueprint('auth', __name__, url_prefix='/auth')

_server_ip= 'ldaps://10.59.72.6'
_port = '636'
_baseDN = ',ou=users,dc=ipo,dc=com'


def check_auth(username, passwd):
    try:
        server = Server(_server_ip, port=int(_port), use_ssl=True, get_info=ALL)
        _connection = Connection(server, 'cn=' + username + _baseDN, passwd, auto_bind=True)
    except Exception as e:
        return False
    return True


@auth.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        if check_auth(form.username.data.strip(), form.password.data):
            user = User.query.filter_by(username=form.username.data).first()
            if user is not None :
                login_user(user, form.remember_me.data)
                return redirect(request.args.get('next') or url_for('dns.index'))
            new_user = User(username=form.username.data)
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user, form.remember_me.data)
            return redirect(request.args.get('next') or url_for('dns.index'))
        flash('无效的用户名或密码!')
        return redirect(url_for('auth.login'))
    return render_template('auth/login.html', form=form)


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('你已经退出。')
    return redirect(url_for('auth.login'))

