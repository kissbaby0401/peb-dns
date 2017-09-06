from datetime import datetime
import hashlib
from flask import current_app, request, url_for
from flask_login import UserMixin, AnonymousUserMixin
from hfdns.extensions import db, login_manager 
import copy


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(64), unique=True, index=True)
    username = db.Column(db.String(64), unique=True, index=True)
    chinese_name = db.Column(db.String(64))
    cellphone = db.Column(db.String(64))
    actived = db.Column(db.Boolean, default=False)
    position = db.Column(db.String(64))
    location = db.Column(db.String(64))
    acitve = db.Column(db.Integer)
    admin = db.Column(db.Integer, index=True, default=0)
    member_since = db.Column(db.DateTime(), default=datetime.now)
    last_seen = db.Column(db.DateTime(), default=datetime.now)


class AnonymousUser(AnonymousUserMixin):
    def can(self, permissions):
        return False

    def is_administrator(self):
        return False


class View(db.Model):
    __tablename__ = 'dns_views'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), index=True)
    data = db.Column(db.Text())
    zones = db.relationship('Zone', backref='view', lazy='dynamic')


class Zone(db.Model):
    __tablename__ = 'dns_zones'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), index=True)
    is_inner = db.Column(db.Integer)
    z_type = db.Column(db.String(64))
    views = db.Column(db.String(64))
    forwarders = db.Column(db.String(64))
    records = db.relationship('Record', backref='zone', lazy='dynamic')
    view_id = db.Column(db.Integer, db.ForeignKey('dns_views.id'))
    

class Record(db.Model):
    __tablename__ = 'dns_records'
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.String(64), index=True)
    host = db.Column(db.String(64))
    record_type = db.Column(db.String(64))
    TTL = db.Column(db.String(64))
    value = db.Column(db.String(64))
    line_type = db.Column(db.String(64), default='')
    comment = db.Column(db.String(64))
    creator = db.Column(db.String(64))
    updator = db.Column(db.String(64))
    status = db.Column(db.String(64), default='enabled')
    enabled = db.Column(db.String(64), default='1')
    alive = db.Column(db.String(64), default='ON')
    create_time = db.Column(db.DateTime(), default=datetime.now)
    update_time = db.Column(db.DateTime(), default=datetime.now)
    zone_id = db.Column(db.Integer, db.ForeignKey('dns_zones.id'))


class Server(db.Model):
    __tablename__ = 'dns_servers'
    id = db.Column(db.Integer, primary_key=True)
    host = db.Column(db.String(64), index=True)
    ip = db.Column(db.String(64))
    env = db.Column(db.String(64))
    dns_type = db.Column(db.String(64))
    status = db.Column(db.String(64), default='初始化中')
    logs = db.Column(db.Text())



class Logs(db.Model):
    __tablename__ = 'logs'
    id = db.Column(db.Integer, primary_key=True)
    operation_time = db.Column(db.DateTime(), default=datetime.now)
    operation_type = db.Column(db.String(64))
    operator = db.Column(db.String(64))
    target_type = db.Column(db.String(64))
    target_name = db.Column(db.String(64))
    target_id = db.Column(db.String(64))
    target_detail = db.Column(db.Text())



