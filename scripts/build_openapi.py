#!/usr/bin/env python3
"""Generate new-endpoints-openapi.json — the endpoints added in this round,
in OpenAPI 3.0 so Apidog (or Swagger UI) can import them in one go."""

import json

ENVELOPE = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "example": "success"},
        "message": {"type": "string"},
        "data": {},
    },
}


def body(props, required=None, example=None):
    """Request body in the app's {"data": {...}} convention."""
    schema = {
        "type": "object",
        "properties": {"data": {"type": "object", "properties": props,
                                **({"required": required} if required else {})}},
        "required": ["data"],
    }
    content = {"schema": schema}
    if example:
        content["example"] = {"data": example}
    return {"required": True, "content": {"application/json": content}}


def ok(description="OK", example=None):
    content = {"schema": {"$ref": "#/components/schemas/Envelope"}}
    if example is not None:
        content["example"] = {"status": "success", "message": "OK", "data": example}
    return {
        "200": {"description": description,
                "content": {"application/json": content}},
        "400": {"description": "Missing or invalid field"},
        "401": {"description": "Not signed in"},
        "403": {"description": "Not allowed, or not your record"},
        "500": {"description": "Server error"},
    }


def q(name, description, schema="string", example=None):
    p = {"name": name, "in": "query", "required": False,
         "description": description, "schema": {"type": schema}}
    if example is not None:
        p["example"] = example
    return p


def path_param(name, description="", example=None):
    p = {"name": name, "in": "path", "required": True,
         "description": description, "schema": {"type": "string"}}
    if example is not None:
        p["example"] = example
    return p


S = {"str": {"type": "string"}, "int": {"type": "integer"},
     "bool": {"type": "boolean"}, "arr": {"type": "array", "items": {"type": "string"}},
     "obj": {"type": "object"}}

paths = {}


def add(path, method, tag, summary, description="", params=None, req=None,
        responses=None, security=None):
    entry = {
        "tags": [tag],
        "summary": summary,
        "description": description,
        "responses": responses or ok(),
    }
    if params:
        entry["parameters"] = params
    if req:
        entry["requestBody"] = req
    if security is not None:
        entry["security"] = security
    paths.setdefault(path, {})[method] = entry


# ── Waswa AI: assistant ──────────────────────────────────────────────────────
add("/assistant/chat", "post", "Waswa AI", "Ask Waswa a question",
    "Answers from the company's own documents and the caller's own data. "
    "A pricing question is never sent to a model.",
    req=body({"message": S["str"], "surface": {"type": "string",
                                               "enum": ["cms", "oliwa_console", "mobile"]},
              "module": S["str"], "conversation_uid": S["str"]},
             required=["message"],
             example={"message": "How many units do I have active?",
                      "surface": "oliwa_console", "module": "Token Subscription"}),
    responses=ok(example={
        "reply": "You have 34 units active.", "model": "<model id>",
        "conversation_uid": "conv-1", "message_uid": "msg-1",
        "verified_answers": [], "audience": "customer", "prompt_version": "v7",
        "router_tier": 3, "latency_ms": 2140, "intent": "fleet_status",
        "evidence": [], "context_unknown": {}}))

add("/assistant/feedback", "post", "Waswa AI", "Rate an answer",
    "Helpful or Wrong on one of Waswa's answers. Customers send no note. "
    "message_uid must be an assistant message in your own conversation; "
    "rating someone else's needs waswa.review, and without it the reply is 404.",
    req=body({"message_uid": S["str"],
              "verdict": {"type": "string", "enum": ["wrong", "unhelpful", "good"]},
              "note": S["str"], "surface": S["str"]},
             required=["message_uid", "verdict"],
             example={"message_uid": "88086cb8-2b36-4051-9adf-8e265272b43c",
                      "verdict": "wrong", "surface": "oliwa_console"}),
    responses=ok(example={"feedback_uid": "fb-1", "verdict": "wrong",
                          "status": "open"}))

for method in ("get", "post"):
    add("/assistant/context", method, "Waswa AI", "What Waswa knows about the caller",
        "Diagnostic: the caller's own context only.",
        responses=ok(example={"scope": {"account_uid": "u-1", "account_root": "mukwano"},
                              "known": {}, "unknown": {}}))
    add("/assistant/knowledge", method, "Waswa AI", "What a document search returns",
        "Without q, lists the documents Waswa can draw on.",
        params=[q("q", "The search"), q("product", "Limit to one product"),
                q("document_type", "Limit to one document type"),
                q("limit", "How many passages", "integer"),
                q("include_unapproved", "Reviewers only")])

# ── Waswa AI Console ─────────────────────────────────────────────────────────
C = "Waswa AI Console"
add("/assistant/console/summary", "get", C, "Review queue counts",
    "Needs waswa.review.")
add("/assistant/console/queue", "get", C, "The review queue",
    "Needs waswa.review.",
    params=[q("kind", "flag, approval, recheck, document (comma-separated)"),
            q("limit", "Max 200", "integer"), q("offset", "", "integer")])
add("/assistant/console/conversations", "get", C, "Conversations",
    "Needs waswa.review.",
    params=[q("surface", "cms, oliwa_console, mobile"),
            q("flagged", "true to show only flagged"),
            q("limit", "Max 100", "integer"), q("offset", "", "integer")])
add("/assistant/console/conversations/{conversation_uid}", "get", C,
    "One conversation with its messages, evidence and feedback",
    "Needs waswa.review.", params=[path_param("conversation_uid")])

add("/assistant/console/answers", "get", C, "Corrections", "Needs waswa.review.",
    params=[q("status", "draft, submitted, approved, rejected, retired"),
            q("q", "Search the question"), q("limit", "", "integer"),
            q("offset", "", "integer")])
add("/assistant/console/answers", "post", C, "Draft a correction",
    "Needs waswa.review. Question and answer are both required.",
    req=body({"question": S["str"], "answer": S["str"],
              "question_variants": S["arr"],
              "audience": {"type": "string", "enum": ["staff", "everyone"]},
              "country_scope": S["str"], "product_uid": S["str"],
              "sensitivity": S["str"], "feedback_uid": S["str"],
              "source_message_uid": S["str"], "based_on_source_uid": S["str"],
              "based_on_note": S["str"], "review_due": S["str"]},
             required=["question", "answer"],
             example={"question": "What does a token cover?",
                      "answer": "A token covers one unit for the period stated on the package.",
                      "audience": "everyone"}))
add("/assistant/console/answers/{answer_uid}", "get", C, "One correction",
    "Needs waswa.review.", params=[path_param("answer_uid")])
add("/assistant/console/answers/{answer_uid}", "post", C, "Edit a correction",
    "Needs waswa.review.", params=[path_param("answer_uid")],
    req=body({"question": S["str"], "answer": S["str"], "audience": S["str"],
              "review_due": S["str"]}))
add("/assistant/console/answers/{answer_uid}/submit", "post", C,
    "Submit a correction for approval", "Needs waswa.review.",
    params=[path_param("answer_uid")])
add("/assistant/console/answers/{answer_uid}/retire", "post", C,
    "Retire a correction", "Needs waswa.review.",
    params=[path_param("answer_uid")], req=body({"reason": S["str"]}))
add("/assistant/console/answers/{answer_uid}/decide", "post", C,
    "Approve or reject a correction", "Needs waswa.approve.",
    params=[path_param("answer_uid")],
    req=body({"decision": {"type": "string", "enum": ["approve", "reject"]},
              "note": S["str"]}, required=["decision"],
             example={"decision": "approve"}))
add("/assistant/console/answers/{answer_uid}/confirm", "post", C,
    "Reconfirm a correction that is due for review", "Needs waswa.approve.",
    params=[path_param("answer_uid")],
    req=body({"review_due": S["str"], "note": S["str"]}))
add("/assistant/console/feedback/{feedback_uid}/resolve", "post", C,
    "Resolve a flag", "Needs waswa.review.",
    params=[path_param("feedback_uid")],
    req=body({"resolution": S["str"], "note": S["str"], "answer_uid": S["str"]},
             required=["resolution"]))

add("/assistant/console/sources", "get", C, "Documents Waswa draws on",
    "Needs waswa.review. Also returns document types, size limit, allowed "
    "extensions and the upload readiness check.",
    params=[q("include_removed", "true to include removed documents"),
            q("include_old", "true to include superseded versions")])
add("/assistant/console/sources/upload", "post", C, "Upload a document",
    "Needs waswa.review. multipart/form-data, not JSON. Max 25 MB; "
    ".pdf, .docx, .xlsx, .md, .txt.",
    req={"required": True, "content": {"multipart/form-data": {"schema": {
        "type": "object",
        "properties": {
            "file": {"type": "string", "format": "binary"},
            "title": S["str"],
            "document_type": {"type": "string", "enum": [
                "procedure", "policy", "manual", "faq", "strategy",
                "user_stories", "kpi", "journey_map", "catalogue", "other"]},
            "authority_level": {"type": "integer", "minimum": 2, "maximum": 6},
            "audience": {"type": "string", "enum": ["staff", "everyone"]},
            "replaces_source_uid": S["str"], "version_label": S["str"],
            "redactions": S["str"]},
        "required": ["file"]}}}})
add("/assistant/console/sources/{source_uid}", "get", C, "One document",
    "Needs waswa.review.", params=[path_param("source_uid")])
add("/assistant/console/sources/{source_uid}/review", "post", C,
    "Approve or reject a document", "Needs waswa.approve.",
    params=[path_param("source_uid")],
    req=body({"decision": S["str"], "note": S["str"]}, required=["decision"]))
add("/assistant/console/sources/{source_uid}/audience", "post", C,
    "Who can see a document", "Needs waswa.approve.",
    params=[path_param("source_uid")],
    req=body({"audience": {"type": "string", "enum": ["staff", "everyone"]}},
             required=["audience"]))
add("/assistant/console/sources/{source_uid}/details", "post", C,
    "Change a document's details", "Needs waswa.approve.",
    params=[path_param("source_uid")],
    req=body({"title": S["str"], "document_type": S["str"],
              "authority_level": S["int"], "version_label": S["str"]}))
add("/assistant/console/sources/{source_uid}/remove", "post", C,
    "Remove a document", "Needs waswa.approve.",
    params=[path_param("source_uid")], req=body({"reason": S["str"]}))
add("/assistant/console/sources/{source_uid}/restore", "post", C,
    "Restore a removed document", "Needs waswa.approve.",
    params=[path_param("source_uid")])
add("/assistant/console/authority-levels", "get", C, "Authority levels",
    "Needs waswa.review.")
for method in ("get", "post"):
    add("/assistant/console/match", method, C, "Preview which corrections match",
        "Needs waswa.review. Not recorded as a real question.",
        params=[q("q", "The question to try"),
                q("audience", "staff or everyone")])

# ── Team ─────────────────────────────────────────────────────────────────────
T = "Team"
add("/team/me", "get", T, "Who am I, and may I manage the team",
    responses=ok(example={"account_uid": "u-1", "account_root": "mukwano",
                          "role": "client_admin", "role_label": "Administrator",
                          "can_manage_team": True,
                          "roles": [{"role": "client_admin", "label": "Administrator"}]}))
add("/team/members", "get", T, "The client's own users",
    "Administrators only. Removed users are left out.",
    responses=ok(example=[{"account_uid": "u-2", "display_name": "Sarah N",
                           "username": "sarah", "email": "sarah@mukwano.co.ug",
                           "role": "client_operator", "role_label": "Operator",
                           "is_admin": False, "status": "active",
                           "date_created": "2026-09-01",
                           "last_login_at": "2026-09-22T08:14:00", "is_me": False}]))
add("/team/members", "post", T, "Add a user",
    "Administrators only. 409 when the username is taken.",
    req=body({"display_name": S["str"], "username": S["str"], "email": S["str"],
              "password": {"type": "string", "minLength": 8},
              "role": {"type": "string",
                       "enum": ["client_admin", "client_operator", "client_viewer"]}},
             required=["display_name", "username", "password", "role"],
             example={"display_name": "Sarah Nakato", "username": "sarah",
                      "email": "sarah@mukwano.co.ug", "password": "choose-a-strong-one",
                      "role": "client_viewer"}),
    responses={**ok(example={"account_uid": "u-2"}),
               "409": {"description": "Username already taken"}})
add("/team/members/{uid}", "put", T, "Change a user's name, role or status",
    "Administrators only. You cannot change your own role or block yourself.",
    params=[path_param("uid", "The user's account_uid")],
    req=body({"display_name": S["str"], "role": S["str"],
              "status": {"type": "string", "enum": ["active", "blocked"]}}))
add("/team/members/{uid}/reset-password", "post", T, "Reset a user's password",
    "Administrators only. The temporary password is shown once.",
    params=[path_param("uid")],
    responses=ok(example={"temporary_password": "T3mp-...", "username": "sarah"}))
add("/team/members/{uid}", "delete", T, "Remove a user",
    "Administrators only. The user is deactivated, not deleted.",
    params=[path_param("uid")])
add("/team/audit", "get", T, "Sign-ins and team changes",
    "Administrators only. The client's own account, newest first, max 500.",
    params=[q("days", "1-365, default 30", "integer", 30),
            q("kind", "all, signins, failed, team", example="all")],
    responses=ok(example=[{"timestamp": "2026-09-22T08:14:00", "who": "sarah",
                           "action": "LOGIN", "detail": "", "ip_address": "102.0.0.1"}]))

# ── Alerts ───────────────────────────────────────────────────────────────────
A = "Alerts"
add("/alerts/run", "post", A, "Run one geofence sweep",
    "Internal (X-Service-Key) or a staff login. live=false is a dry run.",
    req=body({"live": S["bool"]}, example={"live": True}),
    security=[{"bearerAuth": []}, {"serviceKey": []}],
    responses=ok(example={"rules": 12, "units_checked": 240,
                          "units_skipped_no_position": 3, "units_skipped_stale": 5,
                          "units_skipped_unchanged": 180, "first_seen": 0,
                          "alerts": 2, "live": True, "errors": []}))
add("/alerts/health", "get", A, "What the alert engine knows",
    "Staff only (alarms.view or devices.view).",
    responses=ok(example={"geofence_rules": 12, "tracked_unit_zones": 480,
                          "last_sweep": "2026-09-22 14:03:11", "alerts_last_24h": 7}))

# ── Geofences (changed) ──────────────────────────────────────────────────────
G = "Geofences"
SHAPE = {"geozone_shape": {"type": "string", "enum": ["polygon", "circle", "line"]},
         "geozone_shape_params": {"type": "object",
                                  "description": "polygon {points:[{lat,lng}]}, "
                                                 "circle {center:{lat,lng}, radius_m}, "
                                                 "line {points:[...], width_m}"},
         "geozone_color": S["str"], "geozone_label_color": S["str"]}
add("/geozones/create", "post", G, "Create a geofence",
    "The server computes geozone_points from the shape.",
    req=body({"geozone_name": S["str"], "geozone_decription": S["str"],
              "geozone_owner": S["str"], **SHAPE},
             required=["geozone_name", "geozone_owner"],
             example={"geozone_name": "Main depot", "geozone_decription": "Kampala yard",
                      "geozone_owner": "mukwano", "geozone_shape": "circle",
                      "geozone_shape_params": {"center": {"lat": 0.31, "lng": 32.58},
                                               "radius_m": 500}}))
add("/geozones/{geozone_id}/update", "put", G, "Change a geofence",
    params=[path_param("geozone_id")],
    req=body({"new_geozone_name": S["str"], "new_geozone_decription": S["str"],
              "new_geozone_points": S["str"], **SHAPE}))
add("/geozones/{owner_uid}/list/{access_level}/load", "get", G,
    "List a customer's geofences",
    "access_level is 'client' for a customer.",
    params=[path_param("owner_uid"), path_param("access_level", example="client")],
    responses=ok(example=[{"geozone_uid": "gz-1", "geozone_name": "Main depot",
                           "geozone_description": "Kampala yard",
                           "geozone_points": "[[32.58,0.31]]",
                           "geozone_shape": "circle",
                           "geozone_shape_params": {"center": {"lat": 0.31, "lng": 32.58},
                                                    "radius_m": 500},
                           "date_created": "2026-09-20"}]))
add("/geozones/{geozone_id}/details", "get", G, "One geofence",
    params=[path_param("geozone_id")])

# ── Track playback (changed) ─────────────────────────────────────────────────
P = "Track playback"
PLAYBACK = {"device_imei": S["str"], "from_date": S["str"], "to_date": S["str"],
            "from_time": {"type": "string", "description": "HH:MM or HH:MM:SS"},
            "to_time": {"type": "string", "description": "HH:MM or HH:MM:SS"},
            "offset_log": S["int"], "record_count": S["int"]}
EX = {"device_imei": "864636050000000", "from_date": "22-09-2026",
      "to_date": "22-09-2026", "from_time": "08:00", "to_time": "17:30",
      "offset_log": 0, "record_count": 5000}
add("/data-stream/trips/history", "post", P, "Trip history for a unit",
    "from_time and to_time are optional; without them the whole day is returned.",
    req=body(PLAYBACK, required=["device_imei", "from_date", "to_date"], example=EX))
add("/data-stream/trips/history/replay", "post", P, "Positions for playback",
    "Same fields. Page with offset_log; records come back newest first.",
    req=body(PLAYBACK, required=["device_imei", "from_date", "to_date"], example=EX))

# ── Profile (changed) ────────────────────────────────────────────────────────
add("/rbac/users/{user_uid}/permissions", "get", "Profile",
    "A user's own permissions and identity",
    "A user may only ask for their own; anyone else answers 403.",
    params=[path_param("user_uid")],
    responses=ok(example={"role": "client_admin", "role_uid": "r-1",
                          "permissions": [{"permission_uid": "p-1",
                                           "permission_name": "geofences.view",
                                           "permission_description": "",
                                           "permission_module": "geofences"}],
                          "account_type": "client", "is_customer": True,
                          "display_name": "Agatha", "username": "agatha",
                          "client_uid": "mukwano", "client_name": "Mukwano Co Ltd"}))

# ── Events (changed) ─────────────────────────────────────────────────────────
E = "Events and alerts"
EVENT = {"event_name": S["str"], "event_description": S["str"],
         "event_condition": {"type": "string",
                             "enum": ["speed_threshold", "geofence_breach",
                                      "ignition_change", "low_battery", "device_offline"]},
         "event_condition_value": {"type": "string",
                                   "description": "For geofence_breach, a JSON string: "
                                                  "{\"zones\":[uid],\"breach_type\":"
                                                  "\"enter|exit|both\"}"},
         "alert_channels": {"type": "array",
                            "items": {"type": "string",
                                      "enum": ["email", "sms", "whatsapp", "push"]}},
         "alert_email": S["str"], "alert_phone_numbers": S["str"],
         "event_owner_uid": S["str"]}
EVENT_EX = {"event_name": "Left the depot",
            "event_description": "Any unit leaving the Kampala yard",
            "event_condition": "geofence_breach",
            "event_condition_value": "{\"zones\":[\"gz-1\"],\"breach_type\":\"exit\"}",
            "alert_channels": ["email", "whatsapp"],
            "alert_email": "ops@mukwano.co.ug",
            "alert_phone_numbers": "+256770123456",
            "event_owner_uid": "u-1"}
add("/events/create", "post", E, "Create an alert rule",
    "alert_phone_numbers is required when sms or whatsapp is chosen.",
    req=body(EVENT, required=["event_name", "event_condition", "event_owner_uid"],
             example=EVENT_EX))
add("/events/{event_uid}/update", "post", E, "Change an alert rule",
    params=[path_param("event_uid")], req=body(EVENT, example=EVENT_EX))
add("/devices/events/{event_uid}/attach", "post", E, "Attach units to a rule",
    "Only attached units raise an alert.",
    params=[path_param("event_uid")],
    req=body({"device_list": S["arr"]}, required=["device_list"],
             example={"device_list": ["864636050000000"]}))
add("/devices/{device_id}/events/{event_uid}/remove", "put", E,
    "Detach a unit from a rule",
    params=[path_param("device_id"), path_param("event_uid")])

spec = {
    "openapi": "3.0.3",
    "info": {
        "title": "NAVAS / OLIWA — new endpoints",
        "version": "2026.09",
        "description": (
            "The endpoints added in this round: Waswa AI and its review console, "
            "a client's own team and audit trail, the geofence alert engine, and "
            "the changed fields on geofences, track playback, profile and alert "
            "rules.\n\n"
            "Every call carries `Authorization: Bearer <JWT>` from POST /users/auth, "
            "except the public ones (sign-in, refresh, password reset, payment "
            "callbacks, images). Internal services send `X-Service-Key` instead.\n\n"
            "Bodies use the app convention `{\"data\": {...}}`. Replies are always "
            "`{status, message, data}`."),
    },
    "servers": [
        {"url": "https://narvas.3dservices.co.ug", "description": "Production"},
        {"url": "http://127.0.0.1:5000", "description": "Local"},
    ],
    "security": [{"bearerAuth": []}],
    "tags": [
        {"name": "Waswa AI", "description": "The assistant, for every app"},
        {"name": "Waswa AI Console", "description": "Review and approval, staff only"},
        {"name": "Team", "description": "A client's own users and sign-in history"},
        {"name": "Alerts", "description": "The server-side geofence alert engine"},
        {"name": "Geofences", "description": "Shape fields added to create, update and read"},
        {"name": "Track playback", "description": "Start and end times"},
        {"name": "Profile", "description": "Identity returned with permissions"},
        {"name": "Events and alerts", "description": "Alert rules, channels and unit attachment"},
    ],
    "components": {
        "securitySchemes": {
            "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
            "serviceKey": {"type": "apiKey", "in": "header", "name": "X-Service-Key"},
        },
        "schemas": {"Envelope": ENVELOPE},
    },
    "paths": paths,
}

with open("new-endpoints-openapi.json", "w", encoding="utf-8") as handle:
    json.dump(spec, handle, indent=2, ensure_ascii=False)

print(f"{len(paths)} paths, "
      f"{sum(len(v) for v in paths.values())} operations -> new-endpoints-openapi.json")
