import unittest
from decimal import Decimal
from monitor import amount, units, valid_monster, extract, render_email

class MonitorTests(unittest.TestCase):
    def test_brl(self):
        self.assertEqual(amount('R$ 1.299,90'), Decimal('1299.90'))
        self.assertEqual(amount('59.94'), Decimal('59.94'))
    def test_units(self):
        self.assertEqual(units('Monster Energy Kit 12 Latas 473 ml'), 12)
        self.assertEqual(units('Monster 473ml'), 1)
    def test_filter(self):
        self.assertTrue(valid_monster('Monster Energy 473ml'))
        self.assertFalse(valid_monster('Monster Energy 269ml'))
        self.assertFalse(valid_monster('Red Bull 473ml'))
    def test_schema(self):
        page = '''<html><script type="application/ld+json">{"@type":"Product", "name":"Monster Energy Kit 12 Latas 473ml", "image":"https://example.org/a.jpg", "offers":{"@type":"Offer", "priceCurrency":"BRL", "price":"71.88"}}</script></html>'''
        x = extract(page, {'store':'Teste', 'url':'https://example.org/item'})
        self.assertEqual(x['pack'], 12)
        self.assertEqual(x['unit_price'], 5.99)
    def test_aggregate_is_not_offer(self):
        page = '''<script type="application/ld+json">{"@type":"Product", "name":"Monster Energy 473ml", "offers":{"@type":"AggregateOffer", "lowPrice":"5.50"}}</script>'''
        with self.assertRaises(ValueError):
            extract(page, {'store':'Teste', 'url':'https://example.org/item'})
    def test_no_fake_product(self):
        page = '<h1>Monster 269ml</h1><meta property="product:price:amount" content="5.00">'
        with self.assertRaises(ValueError):
            extract(page, {'store':'Teste', 'url':'https://example.org/item'})
    def test_email_escape(self):
        d = [{'name':'Monster <script> 473ml', 'store':'Loja', 'pack':1, 'unit_price':5.99, 'price':5.99, 'shipping_sc':'nao verificado', 'url':'https://example.com', 'image':''}]
        body = render_email(d, 'hoje')
        self.assertNotIn('<script>', body)
        self.assertIn('&lt;script&gt;', body)
if __name__ == '__main__':
    unittest.main()
