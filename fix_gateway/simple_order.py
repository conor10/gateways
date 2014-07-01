class Order(object):
    def __init__(self):
        self._order_id = None
        self._side = None
        self._symbol = None
        self._qty = 0
        self._executed_qty = 0
        self._price = 0.0
        self._currency = None
        self._order_type = None
        self._time_in_force = None
        self._status = None

        @property
        def order_id(self):
            return self._order_id

        @order_id.setter
        def order_id(self, value):
            self._order_id = value

        @property
        def side(self):
            return self._side

        @side.setter
        def side(self, value):
            self._side = value

        @property
        def symbol(self):
            return self._symbol

        @symbol.setter
        def symbol(self, value):
            self._symbol = value

        @property
        def qty(self):
            return self._qty

        @qty.setter
        def qty(self, value):
            self._qty = value

        @property
        def price(self):
            return self._price

        @price.setter
        def price(self, value):
            self._price = value

        @property
        def currency(self):
            return self._price

        @currency.setter
        def currency(self, value):
            self._currency = value

        @property
        def order_type(self):
            return self._order_type

        @order_type.setter
        def order_type(self, value):
            self._order_type = value

        @property
        def time_in_force(self):
            return self._time_in_force

        @time_in_force.setter
        def time_in_force(self, value):
            self._time_in_force = value

        @property
        def status(self):
            return self._status

        @status.setter
        def status(self, value):
            self._status = value


class Execution(object):
    def __init__(self, order_id=None):
        self._order_id = order_id
        self._last_qty = 0
        self._last_price = 0.0
        self._exec_id = None
        self._transact_time = None

    @property
    def order_id(self):
        return self._order_id

    @order_id.setter
    def order_id(self, value):
        self._order_id = value

    @property
    def last_qty(self):
        return self._last_qty

    @last_qty.setter
    def last_qty(self, value):
        self._last_qty = value

    @property
    def last_price(self):
        return self._last_price

    @last_price.setter
    def last_price(self, value):
        self._last_price = value

    @property
    def exec_id(self):
        return self._exec_id

    @exec_id.setter
    def exec_id(self, value):
        self._exec_id = value

    @property
    def transact_time(self):
        return self._transact_time

    @transact_time.setter
    def transact_time(self, value):
        self._transact_time = value