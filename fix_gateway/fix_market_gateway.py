from abc import abstractmethod
import logging
import time
import quickfix as fix

from simple_order import Execution

# TODO: Convert to enums on Python 3
class Side(object):
    BUY = '1'
    SELL = '2'
    SELL_SHORT = '5'


class OrdStatus(object):
    """These values are based on FIX 4.4 OrdStatus (except the _REJECT
    statuses).
    """
    PENDING_NEW = 'A'
    NEW = '0'
    NEW_REJECT = '8'
    PENDING_REPLACE = 'E'
    REPLACED = '5'
    REPLACE_REJECT = '10'
    PENDING_CANCEL = '6'
    CANCELED = '4'
    CANCEL_REJECT = '11'
    PARTIALLY_FILLED = '1'
    FULLY_FILLED = '2'


class RequestType(object):
    NEW = '0'
    AMEND = '1'
    CANCEL = '2'

OrdRejReason = {
    0: 'Broker / Exchange option',
    1: 'Unknown symbol',
    2: 'Exchange closed',
    3: 'Order exceeds limit',
    4: 'Too late to enter',
    5: 'Unknown Order',
    6: 'Duplicate Order (e.g. dupe ClOrdID (11))',
    7: 'Duplicate of a verbally communicated order',
    8: 'Stale Order',
    9: 'Trade Along required',
    10: 'Invalid Investor ID',
    11: 'Unsupported order characteristic12 = Surveillence Option',
    13: 'Incorrect quantity',
    14: 'Incorrect allocated quantity',
    15: 'Unknown account(s)',
    99: 'Other'
}


class OrderType(object):
    MARKET = '1'
    LIMIT = '2'
    STOP = '3'
    STOP_LIMIT = '4'
    MARKET_WITH_LEFTOVER_AS_LIMIT = 'K'
    PEGGED = 'P'


class CxlRejResponseTo(object):
    ORDER_CANCEL_REQUEST = '1'
    ORDER_CANCEL_REPLACE_REQUEST = '2'


class TimeInForce(object):
    DAY = '0'
    GOOD_TILL_CANCEL = '1'
    AT_THE_OPENING = '2'
    IMMEDIATE_OR_CANCEL = '3'
    FILL_OR_KILL = '4'
    GOOD_TILL_CROSSING = '5'
    GOOD_TILL_DATE = '6'
    AT_THE_CLOSE = '7'



class FixMarketAdapter(fix.Application):

    def __init__(self, order_handler):
        super(FixMarketAdapter, self).__init__()
        self.order_handler = order_handler
        self.order_store = FixOrderStore()
        self.log = logging.getLogger(__name__)

    def onCreate(self, sessionID):
        return

    def onLogon(self, sessionID):
        self.log.info("Connected")
        return

    def onLogout(self, sessionID):
        self.log.info("Disconnected")
        return

    def toAdmin(self, sessionID, message):
        return

    def fromAdmin(self, sessionID, message):
        return

    def fromApp(self, message, sessionID):

        msgType = message.getHeader().getField(fix.MsgType())

        if msgType == fix.MsgType_ExecutionReport:
            self._process_execution_report(message)
        elif msgType == fix.MsgType_OrderCancelReject:
            self._process_order_cancel_reject(message)
        else:
            self.log.warn('Unsupported msgType value: {}'.format(msgType))

        return

    def toApp(self, sessionID, message):
        # callback for messages once we're about to send them to a client
        return

    def send_new(self, order):
        order.status = OrdStatus.PENDING_NEW

        message = fix.Message()
        message.getHeader().setField(fix.MsgType(fix.MsgType_NewOrderSingle))

        message.setField(fix.Symbol(order.symbol))
        message.setField(fix.Side(order.side))
        message.setField(fix.OrderQty(order.qty))

        if order.type is not OrderType.MARKET:
            message.setField(fix.Price(order.price))
            message.setField(fix.Currency(order.currency))

        message.setField(fix.OrdType(order.type))
        message.setField(fix.TimeInForce(order.time_in_force))

        cl_ord_id = self.order_store.generate_new_cl_ord_id(order.order_id)
        message.setField(fix.ClOrdID(cl_ord_id))

        self.order_store.update_order_maps(cl_ord_id, order)
        self._send_message(message)

    def send_replace(self, order):
        order.status = OrdStatus.PENDING_REPLACE

        message = fix.Message()
        message.getHeader().setField(
            fix.MsgType(fix.MsgType_OrderCancelReplaceRequest))

        message.setField(fix.Symbol(order.symbol))
        message.setField(fix.Side(order.side))
        message.setField(fix.OrderQty(order.qty))

        if order.type is not OrderType.MARKET:
            message.setField(fix.Price(order.price))

        message.setField(fix.OrdType(order.type))
        message.setField(fix.TimeInForce(order.time_in_force))

        cl_ord_id = self.order_store.generate_next_cl_ord_id(order.order_id)
        message.setField(fix.ClOrdID(cl_ord_id))

        self.order_store.update_order_maps(cl_ord_id, order)
        self._send_message(message)

    def send_cancel(self, order):
        order.status = OrdStatus.PENDING_CANCEL

        message = fix.Message()
        message.getHeader().setField(
            fix.MsgType(fix.MsgType_OrderCancelRequest))

        message.setField(fix.Symbol(order.symbol))
        message.setField(fix.Side(order.side))
        message.setField(fix.OrderQty(order.qty))

        cl_ord_id = self.order_store.generate_next_cl_ord_id(order.order_id)
        message.setField(fix.ClOrdID(cl_ord_id))

        self.order_store.update_order_maps(cl_ord_id, order)
        self._send_message(message)

    def _process_execution_report(self, message):
        cl_ord_id = self._extract_field(fix.ClOrdID(), message)
        exec_type = self._extract_field(fix.ExecType(), message)
        market_order_id = self._extract_optional_field(fix.OrderID(), message)

        order = self.order_store.find_order(cl_ord_id, market_order_id)

        # We only update the market order if it's changed
        self.order_store.store_market_order_id(market_order_id, order.order_id)

        order.order_id = self.order_store.find_order_id(cl_ord_id)

        if exec_type == fix.ExecType_NEW:
            order.status = OrdStatus.NEW
            self.order_handler.on_new_ack(order)

        elif exec_type == fix.ExecType_DONE_FOR_DAY:
            pass

        elif exec_type == fix.ExecType_CANCELED:
            order.status = OrdStatus.CANCELED
            self.order_handler.on_cancel_ack(order)

        elif exec_type == fix.ExecType_REPLACE:
            order.status = OrdStatus.REPLACED
            self.order_handler.on_replace_ack(order)

        elif exec_type == fix.ExecType_PENDING_CANCEL:
            self.log.info('Received pending cancel for order [order id: {}]'
                         .format(order.order_id))

        elif exec_type == fix.ExecType_STOPPED:
            pass

        elif exec_type == fix.ExecType_REJECTED:
            ord_rej_reason = self._extract_field(fix.OrdRejReason(), message)
            self.log.error('Submission rejected, ({}) {}'.format(
                OrdRejReason[ord_rej_reason], ord_rej_reason))
            order.status = OrdStatus.NEW_REJECT
            self.order_handler.on_new_rej(order)

        elif exec_type == fix.ExecType_SUSPENDED:
            pass

        elif exec_type == fix.ExecType_PENDING_NEW:
            self.log.info('Received pending new for order [order id: {}]'
                         .format(order.order_id))

        elif exec_type == fix.ExecType_CALCULATED:
            pass

        elif exec_type == fix.ExecType_EXPIRED:
            pass

        elif exec_type == fix.ExecType_RESTATED:
            pass

        elif exec_type == fix.ExecType_PENDING_REPLACE:
            self.log.info('Received pending replace for order [order id: {}]'
                         .format(order.order_id))

        elif exec_type == fix.ExecType_TRADE:
            exec_id = self._extract_field(fix.ExecID(), message)
            transact_time = self._extract_date_field(fix.TransactTime(),
                                                     message)
            remaining_qty = self._extract_field(fix.LeavesQty(), message)
            executed_qty = self._extract_field(fix.CumQty(), message)
            last_qty = self._extract_field(fix.LastQty(), message)
            last_px = self._extract_field(fix.LastPx(), message)

            order.executed_qty = executed_qty

            execution = Execution(order.order_id)
            execution.exec_id = exec_id
            execution.transact_time = transact_time
            execution.last_price = last_px
            execution.last_qty = last_qty

            if remaining_qty == 0:
                order.status = OrdStatus.FULLY_FILLED
            else:
                order.status = OrdStatus.PARTIALLY_FILLED

            self.order_store.store_exec_id(exec_id, execution)
            self.order_handler.on_execution(order, execution)

        elif exec_type == fix.ExecType_TRADE_CORRECT:
            pass

        elif exec_type == fix.ExecType_TRADE_CANCEL:
            pass

        elif exec_type == fix.ExecType_ORDER_STATUS:
            pass

        else:
            self.log.error('Unknown execType: {}'.format(exec_type))

    def _process_order_cancel_reject(self, message):
        cl_ord_id = self._extract_field(fix.ClOrdID(), message)
        market_order_id = self._extract_field(fix.OrderID(), message)
        cxl_rej_response_to = self._extract_field(fix.CxlRejResponseTo(),
                                                  message)

        order = self.order_store.find_order(cl_ord_id, market_order_id)

        if cxl_rej_response_to == \
                CxlRejResponseTo.ORDER_CANCEL_REPLACE_REQUEST:
            order.status = OrdStatus.REPLACE_REJECT
            self.order_handler.on_replace_rej(order)
        elif cxl_rej_response_to == CxlRejResponseTo.ORDER_CANCEL_REQUEST:
            order.status = OrdStatus.CANCEL_REJECT
            self.order_handler.on_cancel_rej(order)
        else:
            self.log.error('Unknown CxlRejResponseTo value: {}'
                           .format(cxl_rej_response_to))

    def _send_message(self, message):
        try:
            fix.Session.sendToTarget(message)
        except fix.SessionNotFound as e:
            self.log.error('Unable to send message [{}], exception: {}'
                           .format(message, e))

    @staticmethod
    def _extract_field(field, message):
        message.getField(field)
        return field.getValue()

    @staticmethod
    def _extract_optional_field(field, message):
        if message.isSetField(field):
            return FixMarketAdapter._extract_field(field, message)
        else:
            return None

    @staticmethod
    def _extract_date_field(field, message):
        message.getField(field)
        return field.getString()


class FixOrderStore:
    def __init__(self):
        self.cl_ord_id_to_order_id_map = {}
        self.order_id_to_cl_ord_id_map = {}
        self.market_order_id_map = {}
        self.exec_id_map = {}
        self.order_store = {}

        self.log = logging.getLogger(__name__)

    @staticmethod
    def generate_new_cl_ord_id(order_id):
        return order_id + '_1'

    @staticmethod
    def _increment_cl_ord_id(cl_ord_id):
        ref = cl_ord_id.rsplit('_')
        if len(ref) == 2:
            return ref[0] + '_' + str(int(ref[1]) + 1)
        else:
            raise StoreException(
                'Unable to increment ClOrdId: {}'.format(cl_ord_id))

    def generate_next_cl_ord_id(self, order_id):
        if order_id in self.order_id_to_cl_ord_id_map:
            cl_ord_id = self.order_id_to_cl_ord_id_map[order_id]

            if cl_ord_id is not None:
                new_cl_ord_id = self._increment_cl_ord_id(cl_ord_id)
                self.order_id_to_cl_ord_id_map[order_id] = new_cl_ord_id
                return new_cl_ord_id

        raise StoreException('OrderId: {} has no existing ClOrdId '
                             'associated'.format(order_id))

    def update_order_maps(self, cl_ord_id, order):
        if cl_ord_id in self.cl_ord_id_to_order_id_map:
            self.log.warn('ClOrdId: {} is already mapped for Order: {}'
                    .format(cl_ord_id, order.order_id))

        self.cl_ord_id_to_order_id_map[cl_ord_id] = order.order_id

        self.log.debug('Updating current ClOrdId for OrderId {} to {}'
                .format(order.order_id, cl_ord_id))
        self.order_id_to_cl_ord_id_map[order.order_id] = cl_ord_id

        self.store_order(order)

    def find_order_id(self, cl_ord_id):
        if cl_ord_id in self.cl_ord_id_to_order_id_map:
            return self.cl_ord_id_to_order_id_map[cl_ord_id]
        else:
            raise StoreException('Unable to find internal OrderId for '
                                 'ClOrdId: {}'.format(cl_ord_id))

    def find_order(self, cl_ord_id, market_order_id):
        if cl_ord_id in self.cl_ord_id_to_order_id_map:
            order_id = self.cl_ord_id_to_order_id_map[cl_ord_id]
            return self.order_store[order_id]
        elif market_order_id in self.market_order_id_map:
            order_id = self.market_order_id_map[market_order_id]
            return self.order_store[order_id]
        else:
            raise StoreException(
                'Unable to find order for ExecutionReport: '
                '[ClOrdId: {}, MarketOrderId: {}'
                .format(cl_ord_id, market_order_id))

    def store_order(self, order):
        self.order_store[order.order_id] = order

    def store_market_order_id(self, market_order_id, order_id):
        if market_order_id not in self.market_order_id_map:
            self.market_order_id_map[market_order_id] = order_id

    def store_exec_id(self, exec_id, execution):
        self.exec_id_map[exec_id] = execution


class StoreException(Exception):
    pass


class OrderHandler(object):

    @abstractmethod
    def send_new(self, order):
        pass

    @abstractmethod
    def send_replace(self, order):
        pass

    @abstractmethod
    def send_cancel(self, order):
        pass

    @abstractmethod
    def on_execution(self, order, execution):
        pass

    @abstractmethod
    def on_new_ack(self, order):
        pass

    @abstractmethod
    def on_new_rej(self, order):
        pass

    @abstractmethod
    def on_replace_ack(self, order):
        pass

    @abstractmethod
    def on_replace_rej(self, order):
        pass

    @abstractmethod
    def on_cancel_ack(self, order):
        pass

    @abstractmethod
    def on_cancel_rej(self, order):
        pass

    @abstractmethod
    def process_request(self, request_type, order):
        pass

    @abstractmethod
    def publish_response(self, order):
        pass


class FixMarketGateway(OrderHandler):

    def __init__(self, config_file):
        self.order_store = FixOrderStore()
        self.initiator = self._create_fix_socket(config_file)
        self.log = logging.getLogger(__name__)

    def _create_fix_socket(self, config_file):
        settings = fix.SessionSettings(config_file)
        gateway = FixMarketAdapter(self)
        store_factory = fix.FileStoreFactory(settings)
        log_factory = fix.ScreenLogFactory(settings)
        return fix.SocketInitiator(gateway, store_factory, settings,
                                   log_factory)

    def start(self):
        self.initiator.start()

    def process_request(self, request_type, order):
        if request_type == RequestType.NEW:
            self.gateway.send_new(order)
        elif request_type == RequestType.AMEND:
            self.gateway.send_replace(order)
        elif request_type == RequestType.CANCEL:
            self.gateway.send_cancel(order)
        else:
            self.log.error('Invalid request type specified: {}'
                    .format(request_type))

    def publish_response(self, order):
        pass

    def send_new(self, order):
        pass

    def send_replace(self, order):
        pass

    def send_cancel(self, order):
        pass

    def on_execution(self, order, execution):
        pass

    def on_new_ack(self, order):
        pass

    def on_new_rej(self, order):
        pass

    def on_replace_ack(self, order):
        pass

    def on_replace_rej(self, order):
        pass

    def on_cancel_ack(self, order):
        pass

    def on_cancel_rej(self, order):
        pass


def main():
    try:
        gateway = FixMarketGateway('../config/client.cfg')
        gateway.start()

        while 1:
            time.sleep(1)
    except (fix.ConfigError, fix.RuntimeError) as e:
        print(e)

if __name__ == '__main__':
    main()