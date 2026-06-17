from flask import Flask
from flask import Blueprint
from flask import request
import psycopg2
from flask import json
from flask import jsonify
from flask import current_app
import base64
from decimal import Decimal
import base64
import uuid
import pytz
from datetime import datetime
from .globals import require_permission

_products_billing = Blueprint("ProductsBilling", __name__)

timezone = pytz.timezone('Africa/Nairobi')

def response_out(status, message, statusCode, data):
    return jsonify({
        "status": status,
        "message": message,
        "data": data
    }), statusCode


@_products_billing.route("/billing/products/create", methods=["POST"])
@require_permission('products.create')
def CreateNewProduct():

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payloadRequestObject = request.get_json()

    _productName = _payloadRequestObject['data']['product_name'].lower()

    if(str(_productName).strip() == ""):
        return response_out("error", "Product name cannot be empty", 400, None)

    with dbconnect:
        with dbconnect.cursor() as dbcursor:
            dbcursor.execute("SELECT * FROM abi_products_manager WHERE product_name = %s", (str(_productName),))

            if(dbcursor.rowcount > 0):
                return response_out("error", "Product with the same name already exists", 400, None)

            _productUid = str(uuid.uuid4())
            dbcursor.execute("INSERT INTO abi_products_manager (product_uid, product_name) VALUES (%s, %s)", (_productUid, _productName))
            dbconnect.commit()

    return response_out("success", "Product created successfully", 200, {"product_uid": _productUid, "product_name": _productName})


@_products_billing.route("/billing/products/list", methods=["GET"])
@require_permission('products.view_only')
def ListProducts():
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    with dbconnect:
        with dbconnect.cursor() as dbcursor:
            dbcursor.execute("SELECT product_uid, product_name FROM abi_products_manager ORDER BY id DESC")

            if(dbcursor.rowcount == 0):
                return response_out("success", "No products found", 200, [])

            products = dbcursor.fetchall()

    products_list = []
    for product in products:
        products_list.append({
            "product_uid": product[0],
            "product_name": product[1]
        })

    return response_out("success", "Products retrieved successfully", 200, products_list)


@_products_billing.route("/billing/products/delete", methods=["POST"])
@require_permission('products.delete')
def DeleteProduct():
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payloadRequestObject = request.get_json()

    _productUid = _payloadRequestObject['data']['product_uid']

    with dbconnect:
        with dbconnect.cursor() as dbcursor:
            dbcursor.execute("SELECT * FROM abi_products_manager WHERE product_uid = %s", (_productUid,))

            if(dbcursor.rowcount == 0):
                return response_out("error", "Product not found", 404, None)
            
            dbcursor.execute("DELETE FROM abi_products_manager WHERE product_uid = %s", (_productUid,))
            dbconnect.commit()

    return response_out("success", "Product deleted successfully", 200, None)


@_products_billing.route("/billing/products/update", methods=["POST"])
@require_permission('products.update')
def UpdateProduct():
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payloadRequestObject = request.get_json()

    _productUid = _payloadRequestObject['data']['product_uid']
    _newProductName = _payloadRequestObject['data']['new_product_name'].lower()

    if(str(_newProductName).strip() == ""):
        return response_out("error", "New product name cannot be empty", 400, None)

    with dbconnect:
        with dbconnect.cursor() as dbcursor:
            dbcursor.execute("SELECT * FROM abi_products_manager WHERE product_uid = %s", (_productUid,))

            if(dbcursor.rowcount == 0):
                return response_out("error", "Product not found", 404, None)

            dbcursor.execute("UPDATE abi_products_manager SET product_name = %s WHERE product_uid = %s", (_newProductName, _productUid))
            dbconnect.commit()

    return response_out("success", "Product updated successfully", 200, {"product_uid": _productUid, "product_name": _newProductName})