from flask import Blueprint, request, jsonify, current_app, redirect, render_template, flash, url_for,abort
from flask_login import login_user, logout_user, login_required, current_user
from hfdns.extensions import db
from hfdns.models import User, View, Zone, Record, Logs, Server
from hfdns.decorators import permission_required
from collections import OrderedDict
from datatables import ColumnDT, DataTables
from datetime import datetime, timedelta
from ..util import getDNSPodLines, DNSRecord, doCMDWithOutput, getRecordContent, initServer
from ..dns_temp import make_record, DNSZone, DNSView, getETCDclient
import etcd
from jinja2 import Template
import threading
from sqlalchemy import and_, or_

dns = Blueprint('dns', __name__, url_prefix='/dns')


@dns.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'GET':
        
        inner_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 1).all()])
        intercepted_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 2).all()])
        outter_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 0).all()])

        # print(Zone.query.count())
        all_servers = Server.query.all()
        server_num = len(all_servers)
        groups = int(server_num/4) + 1
        counts = (server_num, View.query.count(), Zone.query.count(), Record.query.count())

        # print(current_app.config)

        return render_template('dns/index.html', inner_zones=inner_zones, intercepted_zones=intercepted_zones, outter_zones=outter_zones, counts=counts, all_servers=all_servers)
    elif request.method == 'POST':
        return jsonify(message='OK'), 200


@dns.route('/views', methods=['GET', 'POST'])
@login_required
def views():
    if request.method == 'GET':
        inner_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 1).all()])
        intercepted_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 2).all()])
        outter_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 0).all()])
        # views = View.query.all()
        views = View.query.order_by(View.id.desc()).all()
        # bind_conf_content = "test------bind_conf_content,<br>bind_conf_contentbind_conf_content<br>bind_conf_contentbind_conf_content"
        return render_template('dns/views.html', inner_zones=inner_zones, intercepted_zones=intercepted_zones, outter_zones=outter_zones, views = views)
    elif request.method == 'POST':
        req = request.json
        # print(req)

        action = req.get('action')

        if action == 'create' or action == 'modify':
            v_name = req.get('v_name').strip()
            v_data = req.get('v_data')
            ip_list = [ip.strip() for ip in v_data.split()]
            if action == 'create':
                unique_view = View.query.filter_by(name=v_name).first()
                if unique_view:
                    return jsonify(message='Failed', error_msg='创建失败 !<br \>重复的View！！<br> 相同的名字的View 已存在。')

                new_view = View(name=v_name, data=v_data)
                db.session.add(new_view)
                db.session.flush()
                # view_list = db.session.query(View).all()

                log = Logs(operation_type='添加', operator=current_user.username, target_type='View', target_name=new_view.name, \
                        target_id=int(new_view.id))
                db.session.add(log)

                try:
                    DNSView(new_view).create()
                    # make_view(action, v_name, ip_list, view_list)
                except Exception as e:
                    db.session.rollback()
                    return jsonify(message='Failed', error_msg='操作失败 !!!<br> 错误信息如下：<br>' + str(e))
                db.session.commit()
                return jsonify(message='OK'), 200
            elif action == 'modify':
                view_id = req.get('view_id')

                unique_view = db.session.query(View).filter(and_(View.name==v_name, View.id != int(view_id))).first()
                if unique_view:
                    return jsonify(message='Failed', error_msg='创建失败 !<br \>重复的Zone！！<br> 相同名字的Zone，每种类型域名下只能存在一个！。')

                current_view = View.query.get(int(view_id))
                # if current_view and current_view.name == v_name:
                #     return jsonify(message='Failed', error_msg='修改失败 !<br \>重复的View！！<br> 相同的名字的View 已存在。')
                current_view.name = v_name
                current_view.data = v_data
                db.session.add(current_view)
                log = Logs(operation_type='修改', operator=current_user.username, target_type='View', target_name=current_view.name, \
                        target_id=int(current_view.id))
                db.session.add(log)

                # view_list = db.session.query(View).all()
                try:
                    # make_view(action, v_name, ip_list, view_list)
                    DNSView(current_view).modify()
                except Exception as e:
                    db.session.rollback()
                    return jsonify(message='Failed', error_msg='操作失败 !!!<br> 错误信息如下：<br>' + str(e))
                db.session.commit()
                return jsonify(message='OK'), 200
        else:
            view_id = req.get('view_id')
            current_view = View.query.get(int(view_id))
            # zones_bind_current_view = db.session.query(Zone).filter(Zone.views.like("%" + current_view.name + "%")).all()
            zones_bind_current_view = []
            for zz in Zone.query.all():
                if current_view.name in zz.views.split(','):
                    zones_bind_current_view.append(zz)
            if zones_bind_current_view:
                return jsonify(message='Failed', error_msg='删除失败 !!!<br> 当前View已被以下Zone绑定，请先解除绑定！<br>' + '[ ' + '，'.join([zone.name for zone in zones_bind_current_view]) + ' ]')
            # ip_list = current_view.data.split()
            # v_name = current_view.name
            db.session.delete(current_view)

            log = Logs(operation_type='删除', operator=current_user.username, target_type='View', target_name=current_view.name, \
                    target_id=int(current_view.id))
            db.session.add(log)

            # view_list = db.session.query(View).all()
            try:
                # make_view(action, v_name, ip_list, view_list)
                DNSView(current_view).delete()
            except Exception as e:
                db.session.rollback()
                return jsonify(message='Failed', error_msg='删除失败 !!!<br> 错误信息如下：<br>' + str(e))
            db.session.commit()
            return jsonify(message='OK'), 200


@dns.route('/servers', methods=['GET', 'POST'])
@login_required
def servers():
    if request.method == 'GET':
        inner_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 1).all()])
        intercepted_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 2).all()])
        outter_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 0).all()])
        # servers = Server.query.all()
        servers = Server.query.order_by(Server.id.desc()).all()
        return render_template('dns/servers.html', inner_zones=inner_zones, intercepted_zones=intercepted_zones, outter_zones=outter_zones, servers=servers)
    elif request.method == 'POST':
        req = request.json
        print(req)
        action = req.get('action')

        if action == 'create' or action == 'modify':
            s_host = req.get('s_host')
            s_ip = req.get('s_ip')
            s_env = req.get('s_env')
            s_type = req.get('s_type')
            if action == 'create':
                #判断唯一性，如已存在，返回报错
                unique_server = db.session.query(Server).filter(or_(Server.host==s_host.strip(), Server.ip==s_ip.strip())).all()
                if unique_server:
                    return jsonify(message='Failed', error_msg='创建失败 !<br \>重复的Server！！<br> 相同 Host 或 IP地址 已存在！。')

                new_server = Server(host=s_host.strip(), ip=s_ip.strip(), env=s_env, dns_type=s_type)
                db.session.add(new_server)
                db.session.flush()
                log = Logs(operation_type='添加', operator=current_user.username, target_type='Server', target_name=new_server.host, \
                        target_id=int(new_server.id))
                db.session.add(log)
                db.session.commit()

                app_object = current_app._get_current_object()
                init_cmd = current_app.config['SERVER_INIT_CMD']
                init_server_thread = threading.Thread(target=initServer, args=(init_cmd, app_object, new_server.id))
                init_server_thread.start()
                
                return jsonify(message='OK'), 201
            elif action == 'modify':
                server_id = int(req.get('server_id'))
                current_server = Server.query.get(server_id)
                current_server.host = s_host.strip()
                current_server.ip = s_ip.strip()
                current_server.env = s_env.strip()
                current_server.dns_type = s_type.strip()

                db.session.add(current_server)

                log = Logs(operation_type='修改', operator=current_user.username, target_type='Server', target_name=current_server.host, \
                        target_id=int(current_server.id))
                db.session.add(log)

                db.session.commit()
                return jsonify(message='OK'), 200
        elif action == 'del':
            server_id = int(req.get('server_id'))
            current_server = Server.query.get(server_id)
            db.session.delete(current_server)

            log = Logs(operation_type='删除', operator=current_user.username, target_type='Server', target_name=current_server.host, \
                    target_id=int(current_server.id))
            db.session.add(log)
            db.session.commit()
            return jsonify(message='OK'), 200



@dns.route('/zones', methods=['GET', 'POST'])
@login_required
def zones():
    if request.method == 'GET':
        
        inner_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 1).all()])
        intercepted_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 2).all()])
        outter_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 0).all()])
        views = View.query.all()
        z_views = OrderedDict([(view.name, view.name) for view in views])

        selections = {'z_views': z_views}
        return render_template('dns/zones.html', inner_zones=inner_zones, intercepted_zones=intercepted_zones, outter_zones=outter_zones, selections = selections)

    elif request.method == 'POST':
        req = request.json
        
        action = req.get('action')
        z_name = req.get('z_name')
        z_type = req.get('z_type')
        z_is_inner = req.get('is_inner')
        z_views = req.get('z_views')
        z_forwarders = req.get('z_forwarders')

        if action == 'create':
            unique_zone = db.session.query(Zone).filter(and_(Zone.name==z_name.strip(), Zone.is_inner.in_((1,2)))).first()
            if unique_zone:
                return jsonify(message='Failed', error_msg='创建失败 !<br \>重复的Zone！！<br> 相同名字的Zone，每种类型域名下只能存在一个！。')

            if z_type == 'forward only':
                z_forwarders = '; '.join([ip.strip() for ip in z_forwarders.strip().split()]) + ';'
            new_zone = Zone(name=z_name.strip(), z_type=z_type.strip(), is_inner=int(z_is_inner), views=','.join(z_views), forwarders=z_forwarders)
            db.session.add(new_zone)
            db.session.flush()
            log = Logs(operation_type='添加', operator=current_user.username, target_type='Zone', target_name=new_zone.name, \
                    target_id=int(new_zone.id))
            db.session.add(log)

            try:
                DNSZone(action, new_zone).create()
            except Exception as e:
                db.session.rollback()
                return jsonify(message='Failed', error_msg='创建失败 !!!<br> 错误信息如下：<br>' + str(e))
            db.session.commit()

            # 初始化 NS 域名
            # @ 86400 IN NS master.a.pa.com
            if new_zone.z_type != "forward only":
                for z_view in z_views:
                    ns_record = Record(host='@', record_type='NS', value='master.'+new_zone.name+'.' , \
                            TTL='86400', line_type=z_view, creator=current_user.username)
                    new_zone.records.append(ns_record)
            db.session.add(new_zone)
            db.session.commit()
            
            return jsonify(message='OK'), 200

        elif action == 'modify':
            # print('modify')
            zone_id = req.get('zone_id')
            unique_zone = db.session.query(Zone).filter(and_(Zone.name==z_name.strip(), Zone.is_inner.in_((1,2))), Zone.id != int(zone_id)).first()
            if unique_zone:
                return jsonify(message='Failed', error_msg='创建失败 !<br \>重复的Zone！！<br> 相同名字的Zone，每种类型域名下只能存在一个！。')

            m_zone = Zone.query.get(int(zone_id))

            pre_views = m_zone.views.split(',')
            record_list = m_zone.records
            m_zone.name = z_name.strip()
            m_zone.z_type = z_type
            m_zone.is_inner = int(z_is_inner)
            m_zone.views = ','.join(z_views)
            if m_zone.z_type == 'forward only':
                m_zone.forwarders = '; '.join([ip.strip() for ip in z_forwarders.strip().split()]) + ';'
            # m_zone.z_forwarders = z_forwarders.split()
            db.session.add(m_zone)
            log = Logs(operation_type='修改', operator=current_user.username, target_type='Zone', target_name=m_zone.name, \
                    target_id=int(m_zone.id))
            db.session.add(log)

            # 清除当前zone 解除绑定view所对应的record
            del_views = set(pre_views) - set(z_views)
            del_records = db.session.query(Record).filter(Record.zone_id==m_zone.id, Record.line_type.in_(tuple(del_views))).all()
            for del_record in del_records:
                db.session.delete(del_record)

            # 添加当前zone新增绑定view时候，所对应的默认record （默认host为@的record）
            add_views = set(z_views) - set(pre_views)
            for add_view in add_views:
                ns_record = Record(host='@', record_type='NS', value='master.'+m_zone.name+'.' , \
                        TTL='86400', line_type=add_view, creator=current_user.username)
                m_zone.records.append(ns_record)
            db.session.add(m_zone)

            try:
                DNSZone(action, m_zone).modify(pre_views)
            except Exception as e:
                db.session.rollback()
                return jsonify(message='Failed', error_msg='修改失败 !!!<br> 错误信息如下：<br>' + str(e))

            db.session.commit()
            return jsonify(message='OK'), 200

        elif action == 'del':
            # print('del')
            zone_id = req.get('zone_id')
            d_zone = Zone.query.get(int(zone_id))
            # record_list = d_zone.records
            record_list = Record.query.filter_by(zone_id = zone_id)
            for record in record_list:
                db.session.delete(record)
            db.session.delete(d_zone)
            log = Logs(operation_type='删除', operator=current_user.username, target_type='Zone', target_name=d_zone.name, \
                    target_id=int(d_zone.id))
            db.session.add(log)
            try:
                DNSZone(action, d_zone).delete()
            except Exception as e:
                db.session.rollback()
                return jsonify(message='Failed', error_msg='创建失败 !!!<br> 错误信息如下：<br>' + str(e))

            db.session.commit()
            return jsonify(message='OK'), 200

        return jsonify(message='Failed', error_msg='操作失败 !!!<br> 不支持此种操作类型：<br>' + str(action))



@dns.route('/intercepted/<zone>', methods=['GET', 'POST'])
@dns.route('/inner/<zone>', methods=['GET', 'POST'])
@login_required
def inner_records(zone):
    # prod_zones = ['a.pa.com', 'd.pa.com', 'p.pa.com']
    if request.method == 'GET':
        inner_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 1).all()])
        intercepted_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 2).all()])
        outter_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 0).all()])
        # print(inner_zones)
        inner_record_types = current_app.config['INNER_TYPES']
        ttl_list = current_app.config['TTL_LIST']

        zone_type = request.path.split('/')[-2]
        is_inner = 0
        if zone_type == 'inner':    
            is_inner = 1 
        elif zone_type == 'intercepted':
            is_inner = 2

        current_zone = Zone.query.filter_by(is_inner=is_inner,name=zone.replace('_', '.')).first()
        inner_lines = current_zone.views.split(',')
        selections = {'r_type': inner_record_types, 'r_line':inner_lines, 'r_ttl':ttl_list}
        return render_template('dns/records.html', inner_zones=inner_zones, intercepted_zones=intercepted_zones, outter_zones=outter_zones, selections=selections, current_zone=current_zone)

    elif request.method == 'POST':
        # print(request.form)
        # print(request.json)
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
        if action == 'create' or action == 'modify':
            r_host = req.get('r_host').strip()
            r_type = req.get('r_type')
            r_value = req.get('r_value').strip()
            r_ttl = req.get('r_ttl')
            r_line = req.get('r_line')
            r_comment = req.get('r_comment').strip()

            if action == 'create':
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
                
                # 如default，所有每个view都添加一条record
                if r_line.strip() == "default":
                    for line in all_lines:
                        new_record = Record(host=r_host, record_type=r_type, value=r_value, \
                                TTL=r_ttl, line_type=line.strip(), comment=r_comment, creator=current_user.username)
                        current_zone.records.append(new_record)
                else:
                    new_record = Record(host=r_host, record_type=r_type, value=r_value, \
                            TTL=r_ttl, line_type=r_line.strip(), comment=r_comment, creator=current_user.username)
                    current_zone.records.append(new_record)

                db.session.add(current_zone)
                db.session.flush()
                
                log = Logs(operation_type='添加', operator=current_user.username, target_type=z_type_zh, target_name=new_record.host, \
                        target_id=int(new_record.id), target_detail=getRecordContent(new_record))
                db.session.add(log)
                # record_list = current_zone.records
                # record_list = db.session.query(Record).filter(Record.zone_id == current_zone.id, Record.line_type == new_record.line_type, Record.host != '@').all()
                try:
                    if r_line.strip() == "default":
                        for line in all_lines:
                            record_list = db.session.query(Record).filter(Record.zone_id == current_zone.id, Record.line_type == line.strip(), Record.host != '@').all()
                            make_record(line, zone_name, record_list)
                    else:
                        record_list = db.session.query(Record).filter(Record.zone_id == current_zone.id, Record.line_type == r_line.strip(), Record.host != '@').all()
                        make_record(r_line, zone_name, record_list)
                except Exception as e:
                    db.session.rollback()
                    return jsonify(message='Failed', error_msg='创建失败 !!!<br> 错误信息如下：<br>' + str(e))
                db.session.commit()
                return jsonify(message='OK'), 200
            elif action == 'modify':
                record_id = int(req.get('record_id'))

                unique_record = Record.query.filter(Record.id!=record_id, Record.zone_id==current_zone.id, Record.host==r_host, Record.line_type==r_line).first()
                if unique_record:
                    return jsonify(message='Failed', error_msg='修改失败 ！！<br \>重复的记录！！<br> 同一个Zone下面，相同的主机和线路类型 只能存在一个。')

                record = Record.query.get(record_id)
                r_line_pre = record.line_type
                log = Logs(operation_type='修改', operator=current_user.username, target_type=z_type_zh, target_name=record.host,\
                        target_id=int(record.id), target_detail=getRecordContent(record))
                db.session.add(log)
                record.host = r_host
                record.record_type = r_type
                record.value = r_value
                record.TTL = r_ttl
                record.line_type = r_line
                record.comment = r_comment
                db.session.add(record)

                try:
                    # 如线路类型更改， 需要渲染两个zone.xxx文件，更改之前的减少一个，更改之后的添加一个
                    if r_line_pre != r_line:
                        record_list_pre = db.session.query(Record).filter(Record.zone_id == current_zone.id, Record.line_type == r_line_pre, Record.host != '@').all()
                        make_record(r_line_pre, zone_name, record_list_pre)
                    record_list = db.session.query(Record).filter(Record.zone_id == current_zone.id, Record.line_type == record.line_type, Record.host != '@').all()
                    make_record(r_line, zone_name, record_list)
                except Exception as e:
                    db.session.rollback()
                    return jsonify(message='Failed', error_msg='更改失败 !!!<br> 错误信息如下：<br>' + str(e))

                db.session.commit()
                return jsonify(message='OK'), 200

        elif action == 'del':
            record = Record.query.get(int(req.get('record_id')))
            db.session.delete(record)
            log = Logs(operation_type='删除', operator=current_user.username, target_type=z_type_zh, target_name=record.host, \
                    target_id=int(record.id), target_detail=getRecordContent(record))
            db.session.add(log)
            # record_list = current_zone.records
            record_list = db.session.query(Record).filter(Record.zone_id == current_zone.id, Record.line_type == record.line_type, Record.host != '@').all()
            try:
                # print([record.host for record in record_list])
                make_record(record.line_type, zone_name, record_list)
            except Exception as e:
                db.session.rollback()
                return jsonify(message='Failed', error_msg='删除失败 !!!<br> 错误信息如下：<br>' + str(e))
            db.session.commit()
            return jsonify(message='OK'), 200



# @dns.route('/intercepted/<zone>', methods=['GET', 'POST'])
# @login_required
# def intercepted_records(zone):
#     # prod_zones = ['a.pa.com', 'd.pa.com', 'p.pa.com']
#     if request.method == 'GET':
#         inner_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 1).all()])
#         intercepted_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 2).all()])
#         outter_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 0).all()])
#         # print(inner_zones)
#         inner_record_types = current_app.config['INNER_TYPES']
#         ttl_list = current_app.config['TTL_LIST']

#         current_zone = Zone.query.filter_by(is_inner=2,name=zone.replace('_', '.')).first()
#         inner_lines = current_zone.views.split(',')
#         selections = {'r_type': inner_record_types, 'r_line':inner_lines, 'r_ttl':ttl_list}

#         return render_template('dns/records.html', inner_zones=inner_zones, intercepted_zones=intercepted_zones, outter_zones=outter_zones, selections = selections)
#     elif request.method == 'POST':
#         # print(request.form)
#         # print(request.json)
#         req = request.json
#         print(req)
#         action = req.get('action')
#         zone_type = req.get('zone_type')
#         zone_name = req.get('zone_name')
#         # dns_script = current_app.config['BX_SCRIPT_DIR'] if zone_name in prod_zones else current_app.config['OFFICE_SCRIPT_DIR']

#         if action == 'create' or action == 'modify':
#             is_inner = 0
#             if zone_type == 'inner':    
#                 is_inner = 1 
#             elif zone_type == 'intercepted':
#                 is_inner = 2
#             current_zone = Zone.query.filter_by(is_inner = is_inner, name = zone_name).first()
#             r_host = req.get('r_host').strip()
#             # full_host = r_host + "." + zone_name + '.'
#             r_type = req.get('r_type')
#             r_value = req.get('r_value').strip()
#             r_ttl = req.get('r_ttl')
#             r_line = req.get('r_line')
#             r_comment = req.get('r_comment').strip()

#             if action == 'create':
#                 try:
#                     new_record = Record(host=r_host, record_type=r_type, value=r_value, \
#                             TTL=r_ttl, line_type=r_line, comment=r_comment, creator=current_user.username)
#                     current_zone.records.append(new_record)
#                     db.session.add(current_zone)

#                     record_list = current_zone.records
#                     # print('before make record ....')
#                     make_record(r_line, zone_name, record_list)
#                     # print('after make record ....')
#                 except Exception as e:
#                     db.session.rollback()
#                     return jsonify(message='Failed', error_msg='创建失败 !!!<br> 错误信息如下：<br>' + str(e))

#                 db.session.commit()
#                 return jsonify(message='OK'), 200
#             elif action == 'modify':
#                 record = Record.query.get(int(req.get('record_id')))
#                 record.host = r_host
#                 record.record_type = r_type
#                 record.value = r_value
#                 record.TTL = r_ttl
#                 record.line_type = r_line
#                 record.comment = r_comment
#                 try:
#                     db.session.add(record)
#                     record_list = current_zone.records
#                     # print([record.host for record in record_list])
#                     make_record(r_line, zone_name, record_list)
#                 except Exception as e:
#                     db.session.rollback()
#                     return jsonify(message='Failed', error_msg='更改失败 !!!<br> 错误信息如下：<br>' + str(e))

#                 db.session.commit()
#                 return jsonify(message='OK'), 200

#         elif action == 'del':
#             # record_id = req.get('record_id')
#             record = Record.query.get(int(req.get('record_id')))

#             try:
#                 db.session.delete(record)
#                 log = Logs(operation_type='删除', operator=current_user.username, zone_name=zone_name, record_id=int(record_id), record_content=getRecordContent(record))
#                 db.session.add(log)
#                 record_list = current_zone.records
#                 # print([record.host for record in record_list])
#                 make_record(record.line_type, zone_name, record_list)
#             except Exception as e:
#                 db.session.rollback()
#                 return jsonify(message='Failed', error_msg='删除失败 !!!<br> 错误信息如下：<br>' + str(e))
#             db.session.commit()
#             return jsonify(message='OK'), 200



@dns.route('/outter/<zone>', methods=['GET', 'POST'])
@login_required
def outter_records(zone):
    if request.method == 'GET':
        inner_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 1).all()])
        intercepted_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 2).all()])
        outter_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 0).all()])

        outter_record_types = current_app.config['OUTTER_TYPES']
        outter_lines = getDNSPodLines(zone.replace('_', '.'))
        ttl_list = current_app.config['TTL_LIST']

        selections = {'r_type': outter_record_types, 'r_line':outter_lines, 'r_ttl':ttl_list}
        return render_template('dns/records.html', inner_zones=inner_zones, intercepted_zones=intercepted_zones, outter_zones=outter_zones, selections = selections)
    elif request.method == 'POST':
        # print(request.form)
        # print(request.json)
        req = request.json
        # print(req)
        action = req.get('action')
        zone_type = req.get('zone_type')
        zone_name = req.get('zone_name')

        if action == 'create' or action == 'modify':
            is_inner = 0
            zone = Zone.query.filter_by(is_inner = is_inner, name = zone_name).first()
            r_host = req.get('r_host').strip()
            # full_host = r_host + "." + zone_name + '.'
            r_type = req.get('r_type')
            r_value = req.get('r_value').strip()
            r_ttl = req.get('r_ttl')
            r_line = req.get('r_line')
            r_comment = req.get('r_comment')

            if action == 'create':
                dnspod_data = {'domain': zone_name, 'sub_domain':r_host, 'record_type':r_type, 'record_line':r_line, 'value':r_value, 'ttl':r_ttl}
                r = DNSRecord('outter', dnspod_data, '')
                res, output = r.create()
                if res:
                    return jsonify(message='Failed', error_msg='创建失败 !!!<br> 错误信息如下：<br>' + '<br>'.join(output))

                new_record = Record(host=r_host, record_type=r_type, value=r_value, \
                        TTL=r_ttl, line_type=r_line, comment=r_comment, creator=current_user.username)
                new_record.record_id = output['record']['id']
                zone.records.append(new_record)
                db.session.add(zone)

                db.session.flush()
                log = Logs(operation_type='添加', operator=current_user.username, target_type='公网域名', target_name=new_record.host, \
                        target_id=int(new_record.id), target_detail=getRecordContent(new_record))
                db.session.add(log)

                db.session.commit()
                return jsonify(message='OK'), 201

            elif action == 'modify':
                record = Record.query.get(int(req.get('record_id')))

                dnspod_data = {'domain': zone_name, 'record_id':record.record_id, 'sub_domain':r_host.split('.')[0], 'record_type':r_type, 'record_line':r_line, 'value':r_value, 'ttl':r_ttl}
                r = DNSRecord('outter', dnspod_data, '')
                res, output = r.modify()
                if res:
                    return jsonify(message='Failed', error_msg='<br>更改失败 !!!<br> 错误信息如下：<br>' + '<br>'.join(output))

                record.host = r_host
                record.record_type = r_type
                record.value = r_value
                record.TTL = r_ttl
                record.line_type = r_line
                record.comment = r_comment

                db.session.add(record)
                log = Logs(operation_type='修改', operator=current_user.username, target_type='公网域名', target_name=record.host, \
                        target_id=int(record.id), target_detail=getRecordContent(record))
                db.session.add(log)

                db.session.commit()
                return jsonify(message='OK'), 200

        elif action == 'del':
            record_id = req.get('record_id')
            record = Record.query.get(int(record_id))

            dnspod_data = {'domain': zone_name, 'record_id':record.record_id}
            r = DNSRecord('outter', dnspod_data, '')
            res, output = r.delete()
            if res:
                return jsonify(message='Failed', error_msg='<br>删除失败 !!! <br> 错误信息如下：<br>' + '<br>'.join(output))

            db.session.delete(record)

            log = Logs(operation_type='删除', operator=current_user.username, target_type='公网域名', target_name=record.host, \
                    target_id=int(record.id), target_detail=getRecordContent(record))
            db.session.add(log)

            db.session.commit()

            return jsonify(message='OK'), 200


@dns.route('/logs')
@login_required
def logs():
    if request.method == 'GET':
        inner_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 1).all()])
        intercepted_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 2).all()])
        outter_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 0).all()])
        return render_template('dns/logs.html', inner_zones=inner_zones, intercepted_zones=intercepted_zones, outter_zones=outter_zones)


@dns.route('/api/logs', methods=['GET', 'POST'])
@login_required
def logs_api():
    if request.method == 'GET':
        columns = []
        columns.append(ColumnDT(Logs.operation_time))
        columns.append(ColumnDT(Logs.operation_type))
        columns.append(ColumnDT(Logs.target_type))
        columns.append(ColumnDT(Logs.target_name))
        columns.append(ColumnDT(Logs.target_id))
        columns.append(ColumnDT(Logs.operator))
        columns.append(ColumnDT(Logs.target_detail))

        query = db.session.query().select_from(Logs)
        params = request.args.to_dict()
        rowTable = DataTables(params, query, columns)
        res = rowTable.output_result()

        return jsonify(res)


@dns.route('/admin', methods=['GET', 'POST'])
@login_required
@permission_required(2)
def admin():
    if request.method == 'GET':
        inner_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 1).all()])
        intercepted_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 2).all()])
        outter_zones = OrderedDict([(zone.name.replace('.', '_'), zone.name) for zone in Zone.query.filter(Zone.is_inner == 0).all()])
        return render_template('dns/admin.html', inner_zones=inner_zones, intercepted_zones=intercepted_zones, outter_zones=outter_zones)

    if request.method == 'POST':
        req = request.json
        print(req)
        username = req.get('username')
        role = req.get('role')
        try:
            current_user = User.query.filter_by(username=username).first()
            current_user.admin = int(role)
            return jsonify(message='OK'), 200
        except Exception as e:
            return jsonify(message='Failed', error_msg='更改失败 !!!<br> <br \>' + str(e))



@dns.route('/api/bind_conf', methods=['GET', 'POST'])
@login_required
def bind_conf():
    if request.method == 'GET':
        try:
            etcd_client = getETCDclient()
            bind_conf_content = etcd_client.read(current_app.config.get('BIND_CONF')).value
            return jsonify(message='OK', bind_conf=bind_conf_content), 200
        except Exception as e:
            return jsonify(message='Failed', error_msg='获取数据失败 !!!<br> <br \>' + str(e))
    if request.method == 'POST':
        req = request.json
        # print(req)
        try:
            bind_conf_content = req.get('bind_conf')
            etcd_client = getETCDclient()
            etcd_client.write(current_app.config.get('BIND_CONF'), bind_conf_content, prevExist=True)
            return jsonify(message='OK'), 200
        except Exception as e:
            return jsonify(message='Failed', error_msg='提交数据失败 !!!<br> <br \>' + str(e))


@dns.route('/api/all_users', methods=['GET', 'POST'])
@login_required
def users():
    if request.method == 'GET':
        # all_users = User.query.all()
        columns = []
        columns.append(ColumnDT(User.username))
        columns.append(ColumnDT(User.admin))
        columns.append(ColumnDT(User.id))

        query = db.session.query().select_from(User)
        params = request.args.to_dict()
        rowTable = DataTables(params, query, columns)
        res = rowTable.output_result()
        return jsonify(res)


@dns.route('/api/record/<group>/<zone>', methods=['GET', 'POST'])
@login_required
def tables_record(group, zone):
    # print(group, zone)
    is_inner = 0
    if group == 'inner':
        is_inner = 1
    elif group == 'intercepted':
        is_inner = 2
    zone = Zone.query.filter_by(name=zone.replace('_', '.'), is_inner=is_inner).first()
    if not zone:
        abort(404)
    # print(zone.id)

    if request.method == 'GET':
        columns = []
        columns.append(ColumnDT(Record.id))
        columns.append(ColumnDT(Record.host))
        columns.append(ColumnDT(Record.record_type))
        columns.append(ColumnDT(Record.value))
        columns.append(ColumnDT(Record.TTL))
        columns.append(ColumnDT(Record.line_type))
        columns.append(ColumnDT(Record.comment)) # where address is an SQLAlchemy Relation
        # columns.append(ColumnDT(model.update_time))
        columns.append(ColumnDT(Record.alive))
        columns.append(ColumnDT(Record.update_time))

        query = db.session.query().select_from(Record).filter(Record.zone_id==zone.id)
        params = request.args.to_dict()
        rowTable = DataTables(params, query, columns)
        res = rowTable.output_result()
        # print('asdfasfasdfasdfsdfas')
        # print(res)
        return jsonify(res)


@dns.route('/api/zones', methods=['GET', 'POST'])
@login_required
def tables_zone():

    if request.method == 'GET':
        columns = []
        columns.append(ColumnDT(Zone.id))
        columns.append(ColumnDT(Zone.name))
        columns.append(ColumnDT(Zone.is_inner))
        columns.append(ColumnDT(Zone.z_type))
        columns.append(ColumnDT(Zone.views))
        columns.append(ColumnDT(Zone.forwarders))
        columns.append(ColumnDT(Zone.id))

        query = db.session.query().select_from(Zone)
        params = request.args.to_dict()
        rowTable = DataTables(params, query, columns)
        res = rowTable.output_result()
        # print('asdfasfasdfasdfsdfas')
        # print(res)
        return jsonify(res)


@dns.route('/api/server_resolutions', methods=['POST'])
@login_required
def server_resolutions():
        res = request.json
        hours_time = res.get('hours_time')
        if not hours_time:
            hours_time = 1

        time_point_list = []
        time_point_num = 12
        time_period_minute = 5
        
        now = datetime.now()
        time_point_list.append(now)
        for i in range(1, time_point_num + 1):
            time_point = now - timedelta(minutes = time_period_minute * hours_time * i)
            # time_point_str = time_point.strftime("%m-%d %H:%M")
            time_point_list.insert(0, time_point)

        
        
        return jsonify(message='OK')


# @dns.route('/api/inner_selections', methods=['POST'])
# @login_required
# def inner_selections():
#     print(request.form)
#     print(request.get_json())
#     req = request.form
#     if req.get('info_type') == 'r_type':
#         inner_record_types = current_app.config['INNER_TYPES']
#         record_types = [{'id': record_type, 'text': record_type} for record_type in inner_record_types]
#         return jsonify(record_types)
#     elif req.get('info_type') == 'r_ttl':
#         ttl_list = current_app.config['TTL_LIST']
#         ttls = [{'id': ttl, 'text': ttl} for ttl in ttl_list]
#         return jsonify(ttls)
#     elif req.get('info_type') == 'r_line':
#         bx_lines = current_app.config['BX_LINES']
#         office_lines = current_app.config['OFFICE_LINES']
#         lines = [{'id': line, 'text': line} for line in office_lines]
#         return jsonify(lines)


# @dns.route('/api/outter_selections', methods=['POST'])
# @login_required
# def outter_selections():
#     print(request.form)
#     print(request.get_json())
#     req = request.form
#     if req.get('info_type') == 'r_type':
#         outter_record_types = current_app.config['INNER_TYPES']
#         record_types = [{'id': record_type, 'text': record_type} for record_type in outter_record_types]
#         return jsonify(record_types)
#     elif req.get('info_type') == 'r_ttl':
#         ttl_list = current_app.config['TTL_LIST']
#         ttls = [{'id': ttl, 'text': ttl} for ttl in ttl_list]
#         return jsonify(ttls)
#     elif req.get('info_type') == 'r_line':
#         inner_lines = current_app.config['OFFICE_LINES']
#         lines = [{'id': line, 'text': line} for line in inner_lines]
#         return jsonify(lines)