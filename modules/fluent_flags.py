from enum import Enum

class FluentSolverFlags(Enum):
    STEADY = 'steady'
    UNSTEADY_1ST = 'unsteady-1st-order'
    UNSTEADY_2ND = 'unsteady-2nd-order'
    UNSTEADY_2ND_BOUNDED = 'unsteady-2nd-order-bounded'
    
class FluentSpatialSchemes(Enum):
    GRAD_GREENGAUSS_NODE = 'green-gauss-node-based'
    GRAD_GREENGAUSS_CELL = 'green-gauss-cell-based'
    GRAD_LEASTSQUARES = 'least-square-cell-based'
    PRESSURE_PRESTO = 'presto!'
    PRESSURE_SECOND_ORDER = "second-order"
    PRESSURE_STANDARD = "standard"
    PRESSURE_LINEAR = "linear"
    PRESSURE_BODYFORCE = "body-force-weighted"
    FIRST_ORDER_UW = 'first-order-upwind'
    SECOND_ORDER_UW = 'second-order-upwind'
