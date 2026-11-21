"""Kind of architecture per sector, after the campaign model. Written by plan_zones.py: do not edit by hand
(change the rules there and run it again). sectors.py applies it over each sector's "district"."""

ZONES = {
    "CA1": "suburb",      # facades 8 m
    "CA2": "suburb",      # facades 6 m
    "CA3": "suburb",      # facades 7 m
    "CA4": "suburb",      # facades 6 m
    "CA5": "suburb",      # facades 8 m
    "CA6": "suburb",      # facades 8 m
    "CA7": "suburb",      # facades 8 m
    "CA8": "suburb",      # facades 7 m
    "CA9": "suburb",      # facades 8 m
    "CA10": "suburb",      # facades 6 m
    "CA11": "suburb",      # facades 9 m
    "CA12": "suburb",      # facades 6 m
    "CA15": "suburb",      # facades 6 m
    "CA16": "suburb",      # facades 6 m
    "CA17": "suburb",      # facades 7 m
    "CE25": "midtown",      # area Praça Comercial
    "CE26": "midtown",      # area Praça Comercial
    "CE27": "midtown",      # area Praça Comercial
    "CE29": "midtown",      # area Praça Comercial
    "CE30": "midtown",      # area Praça Comercial
    "CE31": "midtown",      # area Praça Comercial
    "CE32": "midtown",      # area Praça Comercial
    "CE33": "midtown",      # area Praça Comercial
    "CE34": "midtown",      # area Praça Comercial
    "CE35": "midtown",      # area Praça Comercial
    "CE36": "midtown",      # area Praça Comercial
    "CE37": "midtown",      # area Praça Comercial
    "CE38": "midtown",      # area Praça Comercial
    "CE39": "midtown",      # area Praça Comercial
    "CN1": "industrial",      # harbour
    "CS4": "victorian",      # area Bairro Residencial
    "CS9": "victorian",      # area Bairro Residencial
    "CS10": "victorian",      # area Bairro Residencial
    "CS11": "victorian",      # area Bairro Residencial
    "CS13": "victorian",      # area Bairro Residencial
    "CS14": "victorian",      # area Bairro Residencial
    "CS16": "victorian",      # area Bairro Residencial
    "CS17": "victorian",      # area Bairro Residencial
    "CS20": "victorian",      # facades 15 m
    "CS21": "victorian",      # area Bairro Residencial
    "CS22": "victorian",      # area Bairro Residencial
    "CS25": "victorian",      # area Bairro Residencial
    "CS26": "victorian",      # area Bairro Residencial
    "CS27": "victorian",      # area Bairro Residencial
    "CW22": "chinatown",      # area Bairro Oriental
    "CW23": "chinatown",      # area Bairro Oriental
    "CW27": "chinatown",      # area Bairro Oriental
    "CW28": "chinatown",      # area Bairro Oriental
    "CW29": "chinatown",      # area Bairro Oriental
    "CW30": "chinatown",      # area Bairro Oriental
    "CW31": "chinatown",      # area Bairro Oriental
    "CW32": "chinatown",      # area Bairro Oriental
    "CW33": "suburb",      # facades 8 m
    "CW34": "industrial",      # area Zona Industrial
    "CW35": "victorian",      # facades 10 m
    "CW36": "victorian",      # facades 10 m
    "CW37": "industrial",      # area Zona Industrial
    "CW38": "industrial",      # area Zona Industrial
    "CW39": "industrial",      # area Zona Industrial
    "CW40": "industrial",      # area Zona Industrial
    "CW41": "industrial",      # area Zona Industrial
    "CW42": "industrial",      # area Zona Industrial
    "CW43": "industrial",      # area Zona Industrial
    "CW44": "industrial",      # area Zona Industrial
    "CW45": "industrial",      # area Zona Industrial
    "CW46": "industrial",      # area Zona Industrial
    "CW47": "industrial",      # area Zona Industrial
    "CW48": "industrial",      # area Zona Industrial
    "CW49": "industrial",      # area Zona Industrial
    "CW50": "industrial",      # area Zona Industrial
    "CW51": "industrial",      # area Zona Industrial
    "CW61": "suburb",      # facades 9 m
    "CW66": "suburb",      # facades 9 m
    "CW69": "suburb",      # facades 9 m
    "CW74": "chinatown",      # area Bairro Oriental
    "CW75": "victorian",      # facades 16 m
    "CW76": "suburb",      # facades 8 m
    "CW77": "industrial",      # area Zona Industrial
    "CW78": "industrial",      # area Zona Industrial
    "CW81": "industrial",      # area Zona Industrial
    "CW85": "suburb",      # facades 10 m
    "CW94": "industrial",      # area Zona Industrial
    "CW95": "industrial",      # area Zona Industrial
    "CW97": "industrial",      # area Zona Industrial
    "CW98": "industrial",      # area Zona Industrial
    "CW110": "industrial",      # area Zona Industrial
    "DN1": "industrial",      # harbour
    "DN2": "industrial",      # harbour
    "DN3": "industrial",      # harbour
    "DN4": "industrial",      # harbour
    "DN5": "industrial",      # harbour
    "DN6": "industrial",      # harbour
    "DN7": "industrial",      # harbour
    "DN8": "industrial",      # harbour
    "ED3": "suburb",      # facades 5 m
    "ED5": "industrial",      # area Zona Industrial
    "ED10": "industrial",      # area Zona Industrial
    "ED14": "suburb",      # facades 10 m
    "ED16": "suburb",      # facades 9 m
    "ED17": "suburb",      # facades 9 m
    "ED19": "victorian",      # area Bairro Residencial
    "ED24": "victorian",      # area Bairro Residencial
    "ED28": "victorian",      # facades 11 m
    "ED29": "victorian",      # facades 11 m
    "ED34": "victorian",      # area Bairro Residencial
    "ED35": "industrial",      # area Zona Industrial
    "ED36": "victorian",      # area Bairro Residencial
    "ED38": "victorian",      # facades 11 m
    "EP1": "midtown",      # area Praça Comercial
    "EP4": "midtown",      # area Praça Comercial
    "EV2": "victorian",      # facades 10 m
    "FN0": "industrial",      # harbour
    "FN1": "industrial",      # harbour
    "FN2": "industrial",      # harbour
    "FN3": "industrial",      # harbour
    "FN4": "industrial",      # harbour
    "FN6": "industrial",      # harbour
    "IOX1": "victorian",      # facades 14 m
    "IOX3": "victorian",      # facades 10 m
    "NH1": "industrial",      # harbour
    "NH2": "industrial",      # harbour
    "PN1": "industrial",      # harbour
    "PN2": "industrial",      # harbour
    "PN3": "industrial",      # harbour
    "PN4": "industrial",      # harbour
    "PP1": "industrial",      # harbour
    "PP2": "industrial",      # harbour
    "PP3": "industrial",      # harbour
}
