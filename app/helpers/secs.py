#####################################################################
# app/helpers/secs.py
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

import threading

import secsgem

from app.helpers import getToolType

events = {}
eventsLock = threading.Lock()
eventNotify = {}


def ceSetup(event, data):
    handler = data['handler']

    handler.clear_collection_events()

    for collectionEvent in handler.registeredCollectionEvents:
        ceid = collectionEvent[0]
        dvids = collectionEvent[1]
        handler.subscribe_collection_event(ceid, dvids)
        if ceid not in handler.collection_events:
            print "configured ceid %d not found" % (ceid)


def _onEvent(eventName, params):
    eventsLock.acquire()

    params["event"] = eventName
    for queue in events:
        events[queue].append(params)

        eventNotify[queue].set()

    eventsLock.release()

    print "_onEvent:", eventName, "params:", params


def queueExists(queue):
    queueAvailable = queue in events

    if not queueAvailable:
        events[queue] = []
        eventNotify[queue] = threading.Event()

    return queueAvailable


def waitForEvents(queue):
    """Wait for events in the event list and return

    :returns: currently available events
    :rtype: list
    """
    eventsLock.acquire()

    if queue not in events:
        events[queue] = []
        eventNotify[queue] = threading.Event()

    if not events[queue]:
        eventsLock.release()

        while not eventNotify[queue].wait(1):
            pass

        eventsLock.acquire()
        eventNotify[queue].clear()

    result = list(events[queue])
    events[queue] = []

    eventsLock.release()

    return result

# setup event handler
eventHandler = secsgem.EventHandler(events={'handler_communicating': ceSetup}, generic_handler=_onEvent)

# setup connection manager
connectionManager = secsgem.HsmsConnectionManager(event_handler=eventHandler)


def addTool(tool):
    # skip disabled tools
    if not tool.enabled:
        return

    toolType = getToolType(tool)

    # add configured tool to the connectionmanager
    handler = connectionManager.add_peer(tool.name, tool.address, tool.port, tool.passive, tool.device_id, toolType)

    ceids = []
    for collection_event in tool.collection_events:
        dvids = []
        for data_value in collection_event.dvs:
            dvids.append(data_value.dvid)

        ceids.append((collection_event.ceid, dvids))

    handler.registeredCollectionEvents = ceids


def stop():
    connectionManager.stop()

def is_int(value):
    try:
        int(value)
        return True
    except ValueError:
        return False
