OWNERSHIP = """
ALTER TABLE orders_orderline ADD CONSTRAINT line_order_seller_fk
FOREIGN KEY (order_id, seller_id) REFERENCES orders_order(id, seller_id) ON DELETE RESTRICT;
ALTER TABLE orders_orderline ADD CONSTRAINT line_product_seller_fk
FOREIGN KEY (product_id, seller_id) REFERENCES catalogue_product(id, seller_id) ON DELETE RESTRICT;
ALTER TABLE orders_refund ADD CONSTRAINT refund_order_checkout_fk
FOREIGN KEY (order_id, checkout_id) REFERENCES orders_order(id, checkout_id) ON DELETE RESTRICT;
"""
OWNERSHIP_REVERSE = """
ALTER TABLE orders_refund DROP CONSTRAINT refund_order_checkout_fk;
ALTER TABLE orders_orderline DROP CONSTRAINT line_product_seller_fk;
ALTER TABLE orders_orderline DROP CONSTRAINT line_order_seller_fk;
"""
