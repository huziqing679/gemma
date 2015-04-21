#####################################################################
# app/controllers/tools.py
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

import time

from app import app, models, helpers
from flask import render_template, redirect, url_for, request, json, abort

@app.route("/tools/")
def tools_list():
    return render_template("tools_list.html", tools = models.Tool.query.all(), connectionManager = helpers.connectionManager)

@app.route("/tools/<toolname>")
def tool_detail(toolname):
    peer = helpers.connectionManager[toolname]
    tool = models.Tool.query.filter(models.Tool.name == toolname).first()

    if peer and peer.connection:
        SVs = sorted(peer.listSVs(), key=lambda SV: SV[0].value)
        ECs = sorted(peer.listECs(), key=lambda EC: EC[0].value)
    else:
        SVs = {}
        ECs = {}

    return render_template("tool_detail.html", peer = peer, tool = tool, modules = helpers.toolHandlers, svids = SVs, ecids = ECs)

@app.route("/tools/<toolname>/restart")
def tool_restart(toolname):
    tool = models.Tool.query.filter(models.Tool.name == toolname).first()

    if helpers.connectionManager.hasConnectionTo(tool.name):
        helpers.connectionManager.removePeer(tool.name, tool.address, tool.port, tool.device_id)

    helpers.addTool(tool)

    return "OK"

@app.route("/tools/<toolname>/comet/<queue>")
def tool_comet(toolname, queue):
    peer = helpers.connectionManager[toolname]

    if peer == None:
        time.sleep(2)
        return json.dumps([])

    events = helpers.waitForEvents(queue)
    return json.dumps(events, default=helpers.jsonEncoder, encoding='latin1')