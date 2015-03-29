#####################################################################
# gemma.py
#
# (c) Copyright 2015, Benjamin Parzella. All rights reserved.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#####################################################################

import sys
import os

import time
import logging

from flask import Flask, render_template, redirect, url_for, request, json, abort
from flask.ext.sqlalchemy import SQLAlchemy

from flask.ext.admin import Admin
from flask.ext.admin.contrib.sqla import ModelView
from wtforms.fields import SelectField

from secsgem import *

def loadModules(path):
    modules=[]
    sys.path.append(path)
    for name in os.listdir(path):
        if name.endswith(".py"):
            #strip the extension
            module = name[:-3]
            modules.append((module,module))
            # set the module name in the current global name space:
            globals()[module] = __import__(module)

    return modules

modules = loadModules("toolhandlers")

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'asdfg'

db = SQLAlchemy(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gemma.db'

admin = Admin(app)

class ToolView(ModelView):
    form_overrides = dict(type=SelectField)
    form_columns = ['name', 'type', 'passive', 'address', 'port', 'device_id', 'enabled', 'collection_events']
    form_args = dict(
        type = dict(
            choices = modules
        ))
    form_widget_args = {
        'collection_events': {
            'disabled': True
        }
    }

class Tool(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True)
    type = db.Column(db.String(80))
    passive = db.Column(db.Boolean)
    address = db.Column(db.String(80))
    port = db.Column(db.Integer)
    device_id = db.Column(db.Integer)
    enabled = db.Column(db.Boolean)
    collection_events = db.relationship('CollectionEvents', backref='tool', lazy='dynamic')

    def __repr__(self):
        return self.name

class CollectionEvents(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tool_id = db.Column(db.Integer, db.ForeignKey('tool.id'), nullable=False)
    ceid = db.Column(db.Integer)

    def __repr__(self):
        return str(self.ceid)

def ceSetup(peer):

    peer.clearCollectionEvents()

    peer.subscribeCollectionEvent(0, peer.ceids[0]["dv"])
    peer.subscribeCollectionEvent(6, peer.ceids[6]["dv"])
    for collectionEvent in peer.registeredCollectionEvents:
        if collectionEvent in peer.ceids:
            peer.subscribeCollectionEvent(collectionEvent, peer.ceids[collectionEvent]["dv"])
        else:
            print "configured ceid %d not found" % (collectionEvent)

if __name__ == "__main__":
    #setup connection manager
    connectionManager = hsmsConnectionManager(postInitCallback = ceSetup)

    def addTool(tool):
        #skip disabled tools
        if not tool.enabled:
            return

        #set default handler
        toolType = secsDefaultHandler

        #check if module loaded for tooltype
        if tool.type in globals():
            #get loaded module
            module = globals()[tool.type]
            #check if module has class for tooltype
            if tool.type in module.__dict__:
                #get loaded class
                classType = module.__dict__[tool.type]
                #check if class is correct type
                if issubclass(classType, secsDefaultHandler):
                    toolType = classType

        #add configured tool to the connectionmanager
        peer = connectionManager.addPeer(tool.name, tool.address, tool.port, tool.passive, tool.device_id, toolType)

        ceids = []
        for collection_event in tool.collection_events:
            ceids.append(collection_event.ceid)

        peer.registeredCollectionEvents = ceids

    #create database
    db.create_all()

    # instanciate all configured tools
    for tool in Tool.query.all():
        addTool(tool)

    #web functions
    @app.route("/tools/")
    def tools_list():
        return render_template("tools_list.html", tools = Tool.query.all(), connectionManager = connectionManager)

    @app.route("/tools/<toolname>")
    def tools_detail(toolname):
        peer = connectionManager[toolname]
        tool = Tool.query.filter(Tool.name == toolname).first()

        if peer and peer.connection:
            SVs = sorted(peer.listSVs(), key=lambda SV: SV[0].value)
            ECs = sorted(peer.listECs(), key=lambda EC: EC[0].value)
        else:
            SVs = {}
            ECs = {}

        return render_template("tools_detail.html", peer = peer, tool = tool, modules = modules, svids = SVs, ecids = ECs)

    @app.route("/tools/<toolname>/update", methods=['POST'])
    def tool_update(toolname):
        if request.method == 'POST':
            tool = Tool.query.filter(Tool.name == toolname).first()

            restartRequired = False

            formEnabled = (request.form["enabled"] == "true")
            formType = request.form["type"]
            formAddress = request.form["address"]
            formPort = request.form["port"]
            formDeviceID = request.form["deviceID"]
            formPassive = (request.form["passive"] == "true")

            if not formEnabled == tool.enabled:
                logging.info("tool_update("+toolname+"): Enabled changed, reconnect required")
                restartRequired = True
            if not formType == tool.type:
                logging.info("tool_update("+toolname+"): Type changed, reconnect required")
                restartRequired = True
            if not formAddress == tool.address:
                logging.info("tool_update("+toolname+"): Address changed, reconnect required")
                restartRequired = True
            if not int(formPort) == tool.port:
                logging.info("tool_update("+toolname+"): Port changed, reconnect required")
                restartRequired = True
            if not int(formDeviceID) == tool.device_id:
                logging.info("tool_update("+toolname+"): DeviceID changed, reconnect required")
                restartRequired = True
            if not formPassive == tool.passive:
                logging.info("tool_update("+toolname+"): Passive changed, reconnect required")
                restartRequired = True

            if restartRequired:
                if connectionManager.hasConnectionTo(tool.name):
                    connectionManager.removePeer(tool.name, tool.address, tool.port, tool.device_id)

            tool.enabled = formEnabled
            tool.type = formType
            tool.address = formAddress
            tool.port = formPort
            tool.device_id = formDeviceID
            tool.passive = formPassive

            db.session.commit()

            if restartRequired:
                addTool(tool)

            return "OK"
        else:
            return "NOGET"

    @app.route("/tools/<toolname>/comet/<queue>")
    def tools_comet(toolname, queue):
        peer = connectionManager[toolname]

        if peer == None:
            abort(404)

        events = peer.waitForEvents(queue)
        return json.dumps(events)

    @app.route("/tools/<toolname>/terminal/<TID>", methods=['POST', 'GET'])
    def tools_terminal(toolname, TID):
        peer = connectionManager[toolname]

        if peer == None:
            abort(404)

        if request.method == 'POST':
            peer.sendEquipmentTerminal(int(TID), request.form["text"].encode('ascii','replace'))

        return "OK"

    @app.route("/tools/<toolname>/sv/<svid>")
    def tools_sv(toolname, svid):
        peer = connectionManager[toolname]
        result = peer.requestSV(int(svid))

        print type(result)

        if isinstance(result, list):
            return str(result)

        return str(result.value)

    @app.route("/tools/<toolname>/ec/<ecid>", methods=['POST', 'GET'])
    def tools_ec(toolname, ecid):
        peer = connectionManager[toolname]
        if request.method == 'POST':
            result = peer.requestEC(int(ecid))
            result.value = int(request.form["value"])
            result = peer.setEC(int(ecid), result)

            return str(ord(result.value[0]))
        else:
            result = peer.requestEC(int(ecid))

            return str(result.value)

    @app.route("/")
    def hello():
        tools = Tool.query.all()

        return "Hello World!"

    #register admin interface for tool table
    admin.add_view(ToolView(Tool, db.session))
    admin.add_view(ModelView(CollectionEvents, db.session))

    #run webapp
    app.run(host="0.0.0.0", port=4999, debug=True, use_reloader=False, threaded=True)

    #disconnect all connections
    connectionManager.stop()
