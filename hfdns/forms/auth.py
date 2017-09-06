
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import Required, Length, Email, Regexp, EqualTo
from wtforms import ValidationError
from ..models import User


class LoginForm(FlaskForm):
    username = StringField('JIRA账号', validators=[Required(), Length(1, 64)])
    password = PasswordField('JIRA账号', validators=[Required()])
    remember_me = BooleanField('记住我')
    submit = SubmitField('登 录')