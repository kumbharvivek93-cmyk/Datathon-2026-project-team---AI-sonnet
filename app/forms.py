"""Validated Flask-WTF forms used by the authentication blueprint."""

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    """Credentials form for the interactive platform login."""

    username = StringField(
        "Username",
        validators=[DataRequired(), Length(min=3, max=80)],
        render_kw={"autocomplete": "username"},
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=256)],
        render_kw={"autocomplete": "current-password"},
    )
    remember = BooleanField("Remember me")
    submit = SubmitField("Sign in")
