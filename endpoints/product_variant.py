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

_products_variant = Blueprint("ProductsVariant", __name__)

timezone = pytz.timezone('Africa/Nairobi')

def response_out(status, message, statusCode, data):
    return jsonify({
        "status": status,
        "message": message,
        "data": data
    }), statusCode

@_products_variant.route("/billing/products/variant/create", methods=["POST"])
@require_permission('products.variants.create')
def CreateNewProductVariant():

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payloadRequestObject = request.get_json()

    _productUid = _payloadRequestObject['data']['product_uid']
    _variantName = _payloadRequestObject['data']['variant_name'].lower()
    _variantBillingType = _payloadRequestObject['data']['billing_type'].lower()
    _variantPrice = Decimal(str(_payloadRequestObject['data']['variant_price']))
    _variantBillingCurrency = _payloadRequestObject['data']['billing_currency'].upper()

    if(str(_variantName).strip() == ""):
        return response_out("error", "Variant name cannot be empty", 400, None)
    if(str(_variantBillingType).strip() == ""):
        return response_out("error", "Billing type cannot be empty", 400, None)
    if(str(_variantBillingCurrency).strip() == ""):
        return response_out("error", "Billing currency cannot be empty", 400, None)
    if(_variantPrice < Decimal('0.00')):
        return response_out("error", "Variant price cannot be negative", 400, None)
    if(_productUid.strip() == ""):
        return response_out("error", "Product UID cannot be empty", 400, None)
    
    with dbconnect:
        with dbconnect.cursor() as dbcursor:
            dbcursor.execute("SELECT id FROM abi_product_variants WHERE variant_name = %s AND product_uid = %s", (str(_variantName), str(_productUid),))

            if(dbcursor.rowcount > 0):
                return response_out("error", "Variant with the same name already exists for this product", 400, None)
            
            _variantUid = str(uuid.uuid4())

            dbcursor.execute("INSERT INTO abi_product_variants (variant_uid, product_uid, variant_name, billing_type, billing_amount, billing_currency) VALUES (%s, %s, %s, %s, %s, %s)", (_variantUid, _productUid, _variantName, _variantBillingType, _variantPrice, _variantBillingCurrency))
            dbconnect.commit()

            return response_out("success", "Product variant created successfully", 200, {"variant_uid": _variantUid, "product_uid": _productUid, "variant_name": _variantName, "billing_type": _variantBillingType, "billing_amount": _variantPrice, "billing_currency": _variantBillingCurrency})
        

@_products_variant.route("/billing/products/variant/list/<string:product_uid>", methods=["GET"])
@require_permission('products.variants.view_only')
def ListProductVariants(product_uid):
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    with dbconnect:
        with dbconnect.cursor() as dbcursor:
            dbcursor.execute("SELECT variant_uid, variant_name, billing_type, billing_amount, billing_currency FROM abi_product_variants WHERE product_uid = %s ORDER BY id DESC", (str(product_uid),))

            if(dbcursor.rowcount == 0):
                return response_out("success", "No variants found for this product", 200, [])
            
            variants = []
            for row in dbcursor.fetchall():
                variants.append({
                    "variant_uid": row[0],
                    "variant_name": row[1],
                    "billing_type": row[2],
                    "billing_amount": float(row[3]),
                    "billing_currency": row[4]
                })

            return response_out("success", "Product variants retrieved successfully", 200, variants)
        

@_products_variant.route("/billing/products/variant/delete", methods=["POST"])
@require_permission('products.variants.delete')
def DeleteProductVariant():
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payloadRequestObject = request.get_json()

    _variantUid = _payloadRequestObject['data']['variant_uid']

    with dbconnect:
        with dbconnect.cursor() as dbcursor:
            dbcursor.execute("SELECT id FROM abi_product_variants WHERE variant_uid = %s", (str(_variantUid),))

            if(dbcursor.rowcount == 0):
                return response_out("error", "Product variant not found", 404, None)
            
            dbcursor.execute("DELETE FROM abi_product_variants WHERE variant_uid = %s", (str(_variantUid),))
            dbconnect.commit()

            return response_out("success", "Product variant deleted successfully", 200, None)
        

@_products_variant.route("/billing/products/variant/update", methods=["POST"])
@require_permission('products.variants.update')
def UpdateProductVariant():
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payloadRequestObject = request.get_json()

    _variantUid = _payloadRequestObject['data']['variant_uid']
    _variantName = _payloadRequestObject['data']['variant_name'].lower()
    _variantBillingType = _payloadRequestObject['data']['billing_type'].lower()
    _variantPrice = Decimal(str(_payloadRequestObject['data']['variant_price']))
    _variantBillingCurrency = _payloadRequestObject['data']['billing_currency'].upper()

    if(str(_variantName).strip() == ""):
        return response_out("error", "Variant name cannot be empty", 400, None)
    if(str(_variantBillingType).strip() == ""):
        return response_out("error", "Billing type cannot be empty", 400, None)
    if(str(_variantBillingCurrency).strip() == ""):
        return response_out("error", "Billing currency cannot be empty", 400, None)
    if(_variantPrice < Decimal('0.00')):
        return response_out("error", "Variant price cannot be negative", 400, None)
    if(_variantUid.strip() == ""):
        return response_out("error", "Variant UID cannot be empty", 400, None)
    
    with dbconnect:
        with dbconnect.cursor() as dbcursor:
            dbcursor.execute("SELECT id FROM abi_product_variants WHERE variant_uid = %s", (str(_variantUid),))

            if(dbcursor.rowcount == 0):
                return response_out("error", "Product variant not found", 404, None)
            
            dbcursor.execute("UPDATE abi_product_variants SET variant_name = %s, billing_type = %s, billing_amount = %s, billing_currency = %s WHERE variant_uid = %s", (_variantName, _variantBillingType, _variantPrice, _variantBillingCurrency, str(_variantUid),))
            dbconnect.commit()

            return response_out("success", "Product variant updated successfully", 200, {"variant_uid": _variantUid, "variant_name": _variantName, "billing_type": _variantBillingType, "billing_amount": _variantPrice, "billing_currency": _variantBillingCurrency})
        