from flask_login import login_required
from flask import Blueprint, url_for, redirect
from .auth import auth
from .dns import dns


main = Blueprint('main', __name__)

@main.route('/')
@login_required
def index():
    return redirect(url_for('dns.index'))