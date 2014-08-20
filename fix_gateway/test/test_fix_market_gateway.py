import unittest

from mock import Mock
from mock import patch

from fix_gateway.simple_order import Order
from fix_gateway.fix_market_gateway import *


class TestFixMarketAdapter(unittest.TestCase):
    def setUp(self):
        with patch('fix_gateway.fix_market_gateway.OrderHandler') as \
                self.handler:
            self.adapter = FixMarketAdapter(self.handler)

    def test_extract_field(self):
        message = fix.Message()
        message.setField(fix.Symbol("TEST"))

        self.assertEqual(
            "TEST",
            self.adapter._extract_field(fix.Symbol(), message))

    def test_extract_optional_field(self):
        message = fix.Message()

        self.assertEqual(
            None,
            self.adapter._extract_optional_field(fix.Symbol(), message))

    def test_extract_date_field(self):
        message = fix.Message()
        message.setField(fix.TransactTime())

        # Unfortunately we cannot instantiate UtcTimeStamp in Quickfix to
        # create a custom time, so we have to use the current time
        # and hope that the milliseconds don't roll the second between the
        # two dates being compared
        self.assertEqual(
            time.strftime('%Y%m%d-%H:%M:%S', time.gmtime()),
            self.adapter._extract_date_field(fix.TransactTime(), message))

    def test_send_new(self):
        self.adapter._send_message = Mock()

        order = Order()
        order.order_id = '12345'
        order.symbol = "TEST"
        order.side = Side.BUY
        order.qty = 10
        order.type = OrderType.LIMIT
        order.price = 123.456
        order.currency = "GBP"
        order.time_in_force = TimeInForce.DAY

        self.adapter.send_new(order)

        message = self.adapter._send_message.call_args[0][0]
        self.assertTrue(self.adapter._send_message.called)
        self.assertEqual(
            '9=63|35=D|11=12345_1|15=GBP|38=10|40=2|44=123.456|54=1|55=TEST'
            '|59=0'
            '|10=249|'.replace('|', '\x01'),
            message.toString())

    def test_send_replace(self):
        self.adapter._send_message = Mock()
        self.adapter.order_store.update_order_maps('12345_1',
                                                   _get_test_order())

        order = Order()
        order.order_id = '12345'
        order.symbol = "TEST"
        order.side = Side.BUY
        order.qty = 10
        order.type = OrderType.LIMIT
        order.price = 123.456
        order.currency = "GBP"
        order.time_in_force = TimeInForce.DAY

        self.adapter.send_replace(order)

        message = self.adapter._send_message.call_args[0][0]
        self.assertTrue(self.adapter._send_message.called)
        self.assertEqual(
            '9=56|35=G|11=12345_2|38=10|40=2|44=123.456|54=1|55=TEST'
            '|59=0|10=130|'.replace('|', '\x01'),
            message.toString())

    def test_send_cancel(self):
        self.adapter._send_message = Mock()
        self.adapter.order_store.update_order_maps('12345_1',
                                                   _get_test_order())

        order = Order()
        order.order_id = '12345'
        order.symbol = "TEST"
        order.side = Side.BUY
        order.qty = 30

        self.adapter.send_cancel(order)

        message = self.adapter._send_message.call_args[0][0]
        self.assertTrue(self.adapter._send_message.called)
        self.assertEqual(
            '9=35|35=F|11=12345_2|38=30|54=1|55=TEST|10=199|'.replace('|',
                                                                   '\x01'),
            message.toString())

    def test_process_execution_report_fill(self):
        self.adapter.order_store.update_order_maps('12345_1',
                                                   _get_test_order())

        message = fix.Message(
            '35=8|6=0|11=12345_1|14=0|17=123|31=45.6|32=5|37=Order1|38=10000'
            '|39=0|54=1|55=TEST|60=20121105-23:25:25|150=F|151=15'
            '|'.replace('|', '\x01'), False)
        self.adapter._process_execution_report(message)

        self.assertTrue(self.handler.on_execution.called)
        order = self.handler.on_execution.call_args[0][0]
        execution = self.handler.on_execution.call_args[0][1]

        self.assertEqual('12345', order.order_id)
        self.assertEqual(OrdStatus.PARTIALLY_FILLED, order.status)

        self.assertEqual('12345', execution.order_id)
        self.assertEqual('123', execution.exec_id)
        self.assertEqual(45.6, execution.last_price)
        self.assertEqual(5, execution.last_qty)
        self.assertEqual('20121105-23:25:25',
                         execution.transact_time)

    def test_process_execution_report_new(self):
        self.adapter.order_store.update_order_maps('12345_1',
                                                   _get_test_order())

        message = fix.Message(
            '35=8|11=12345_1|17=54321|37=123|55=TEST|103=3|150=0|'.replace('|',
                                                                   '\x01'),
            False)
        self.adapter._process_execution_report(message)

        self.assertTrue(self.handler.on_new_ack)
        order = self.handler.on_new_ack.call_args[0][0]

        self.assertEqual('12345', order.order_id)
        self.assertEqual(OrdStatus.NEW, order.status)

    def test_process_execution_report_new_rej(self):
        self.adapter.order_store.update_order_maps('12345_1',
                                                   _get_test_order())

        message = fix.Message(
            '35=8|11=12345_1|55=TEST|103=3|150=8|'.replace('|', '\x01'), False)
        self.adapter._process_execution_report(message)

        self.assertTrue(self.handler.on_new_rej)
        order = self.handler.on_new_rej.call_args[0][0]

        self.assertEqual('12345', order.order_id)
        self.assertEqual(OrdStatus.NEW_REJECT, order.status)

    def test_process_execution_report_canceled(self):
        self.adapter.order_store.update_order_maps('12345_1',
                                                   _get_test_order())

        message = fix.Message(
            '35=8|11=12345_1|37=123|55=TEST|103=3|150=4|'.replace('|', '\x01'),
            False)
        self.adapter._process_execution_report(message)

        self.assertTrue(self.handler.on_cancel_ack)
        order = self.handler.on_cancel_ack.call_args[0][0]

        self.assertEqual('12345', order.order_id)
        self.assertEqual(OrdStatus.CANCELED, order.status)

    def test_process_execution_report_replace(self):
        self.adapter.order_store.update_order_maps('12345_2',
                                                   _get_test_order())

        message = fix.Message(
            '35=8|11=12345_2|41=12345_1|37=123|55=TEST|103=3|150=5|'.replace(
                '|', '\x01'),
            False)
        self.adapter._process_execution_report(message)

        self.assertTrue(self.handler.on_replace_ack)
        order = self.handler.on_replace_ack.call_args[0][0]

        self.assertEqual('12345', order.order_id)
        self.assertEqual(OrdStatus.REPLACED, order.status)

    def test_process_order_cancel_reject_cancel_replace(self):
        self.adapter.order_store.update_order_maps('12345_2',
                                                   _get_test_order())

        message = fix.Message(
            '35=9|11=12345_2|37=123|41=12345_1|39=8|434=2|'.replace('|',
                                                                   '\x01'),
            False
        )
        self.adapter._process_order_cancel_reject(message)

        self.assertTrue(self.handler.on_replace_rej)
        order = self.handler.on_replace_rej.call_args[0][0]

        self.assertEqual('12345', order.order_id)
        self.assertEqual(OrdStatus.REPLACE_REJECT, order.status)

    def test_process_order_cancel_reject_cancel(self):
        self.adapter.order_store.update_order_maps('12345_2',
                                                   _get_test_order())

        message = fix.Message(
            '35=9|11=12345_2|37=123|41=12345_1|39=8|434=1|'.replace('|',
                                                                    '\x01'),
            False
        )
        self.adapter._process_order_cancel_reject(message)

        self.assertTrue(self.handler.on_cancel_rej)
        order = self.handler.on_cancel_rej.call_args[0][0]

        self.assertEqual('12345', order.order_id)
        self.assertEqual(OrdStatus.CANCEL_REJECT, order.status)


class TestFixOrderStore(unittest.TestCase):

    def setUp(self):
        self.store = FixOrderStore()

    def test_generate_new_cl_ord_id(self):
        self.assertEqual('1234_1', self.store.generate_new_cl_ord_id('1234'))

    def test_increment_cl_ord_id(self):
        self.assertEqual(
            '12345_2',
            self.store._increment_cl_ord_id('12345_1'))
        self.assertEqual(
            '12345_100',
            self.store._increment_cl_ord_id('12345_99'))

    def test_increment_cl_ord_id(self):
        with self.assertRaises(StoreException):
            self.store._increment_cl_ord_id('1_2_3_4_2')

    def test_increment_bad_cl_ord_id(self):
        with self.assertRaises(StoreException):
            self.store._increment_cl_ord_id('12345')

    def test_generate_next_cl_ord_id(self):
        order = _get_test_order()
        self.store.update_order_maps('ClOrdId_1', order)

        self.assertEqual(
            'ClOrdId_2',
            self.store.generate_next_cl_ord_id(order.order_id))

    def test_generate_next_cl_ord_id_invalid_id(self):
        with self.assertRaises(StoreException):
            self.store.generate_next_cl_ord_id('Unknown')

    def test_update_order_maps(self):
        order = _get_test_order()
        cl_ord_id = 'ClOrdId_1'
        self.store.update_order_maps(cl_ord_id, order)

        self.assertEqual(
            order.order_id,
            self.store.cl_ord_id_to_order_id_map[cl_ord_id])
        self.assertEqual(
            cl_ord_id,
            self.store.order_id_to_cl_ord_id_map[order.order_id])
        self.assertEqual(
            order,
            self.store.order_store[order.order_id])

    def test_find_order_id(self):
        order = _get_test_order()
        self.store.update_order_maps('ClOrdId_1', order)

        self.assertEqual(order.order_id, self.store.find_order_id(
            'ClOrdId_1'))

    def test_find_order_id_invalid(self):
        with self.assertRaises(StoreException):
            self.store.find_order_id('Unknown')

    def test_find_order_by_cl_ord_id(self):
        order = _get_test_order()
        self.store.update_order_maps('ClOrdId_1', order)

        self.assertEqual(order, self.store.find_order('ClOrdId_1', 'Unknown'))

    def test_find_order_by_market_order_id(self):
        order = _get_test_order()
        self.store.store_market_order_id('MarketId1', order.order_id)
        self.store.store_order(order)

        self.assertEqual(order, self.store.find_order('Unknown', 'MarketId1'))

    def test_find_order_invalid(self):
        with self.assertRaises(StoreException):
            self.store.find_order('Unknown', None)


def _get_test_order():
    order = Order()
    order.order_id = '12345'
    return order


if __name__ == '__main__':
    unittest.main()
