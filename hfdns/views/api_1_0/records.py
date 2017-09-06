from flask import jsonify, request, g, abort, url_for, current_app, current_user
from .. import db
from hfdns.models import Zone, Record
from . import api
# from ..decorators import permission_required
from .errors import forbidden
from sqlalchemy import and_, or_
from hfdns.views.dns_temp import make_record

@api.route('/records/', methods=['GET'])
def get_records():
    records = [record.host for record in db.session.query(Record).filter(Record.zone_id == 51).all()]
    return jsonify(message='OK', records=records)


@api.route('/records/', methods=['GET', 'POST'])
def new_record():
    if request.method == 'GET':
        records = [record.host for record in db.session.query(Record).filter(Record.zone_id == 51).all()]
        return jsonify(message='OK', records=records)
    
    elif request.method == 'POST':
        req = request.json
        action = req.get('action')
        zone_type = req.get('zone_type')
        zone_name = req.get('zone_name')
        # dns_script = current_app.config['BX_SCRIPT_DIR'] if zone_name in prod_zones else current_app.config['OFFICE_SCRIPT_DIR']

        z_type_zh = '外部域名'
        is_inner = 0
        if zone_type == 'inner':
            z_type_zh = '内部域名'
            is_inner = 1 
        elif zone_type == 'intercepted':
            z_type_zh = '劫持域名'
            is_inner = 2

        current_zone = Zone.query.filter_by(is_inner = is_inner, name = zone_name).first()
        r_host = req.get('r_host').strip()
        r_type = req.get('r_type')
        r_value = req.get('r_value').strip()
        r_ttl = req.get('r_ttl')
        r_line = req.get('r_line')
        r_comment = req.get('r_comment').strip()

        all_lines = current_zone.views.split(',')
        # 判断唯一性
        uniq_lines = []
        if r_line.strip() == "default":
            uniq_lines = all_lines
        else:
            uniq_lines = [r_line]
        for uniq_line in uniq_lines:
            unique_record = Record.query.filter_by(zone_id=current_zone.id, host=r_host, line_type=uniq_line).first()
            if unique_record:
                return jsonify(message='Failed', error_msg='创建失败 !<br \>重复的记录！！<br> 同一个Zone下面，相同的主机和线路类型 只能存在一个。')
        
        if r_line.strip() == "default":
            for line in all_lines:
                new_record = Record(host=r_host, record_type=r_type, value=r_value, \
                        TTL=r_ttl, line_type=line, comment=r_comment, creator='cuizhiliang344')
                current_zone.records.append(new_record)
        else:
            new_record = Record(host=r_host, record_type=r_type, value=r_value, \
                    TTL=r_ttl, line_type=r_line, comment=r_comment, creator='cuizhiliang344')
            current_zone.records.append(new_record)

        db.session.add(current_zone)
        db.session.flush()
        
        record_list = db.session.query(Record).filter(and_(Record.zone_id == current_zone.id, Record.line_type == new_record.line_type, Record.host != '@')).all()
        try:
            if r_line.strip() == "default":
                for line in all_lines:
                    make_record(line, zone_name, record_list)
            else:
                make_record(r_line, zone_name, record_list)
        except Exception as e:
            db.session.rollback()
            return jsonify(message='Failed', error_msg='创建失败 !!!<br> 错误信息如下：<br>' + str(e))
        db.session.commit()
        return jsonify(message='OK'), 200

