import argparse
import csv
import logging
import os
from ast import Name
from sre_constants import LITERAL

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, RDF, RDFS, XSD
from slugify import slugify

ROW_ID = "lfd. Nr."
ROW_BUILDING = "Liegenschaft"
ROW_STREET = "Strasse, Haus-Nr."
ROW_ZIP = "PLZ"
ROW_LOCATION = "Ort"
ROW_HEATING_TYPE = "Art der Wärmeversorgung"
ROW_FLOOR_AREA = "NRF Summe Gebäude"
ROW_COMMENT = "Bemerkungen"

# Vocabulary Namespaces

CUBE = Namespace("https://cube.link/")
SCHEMA = Namespace("https://schema.org/")
VCARD = Namespace("http://www.w3.org/2006/vcard/ns#")
BERLIN_BASE = Namespace("https://berlin.github.io/")
CONSUMPTION = Namespace(f"{BERLIN_BASE}lod-energyconsumption/")
ENERPROP = Namespace(f"{CONSUMPTION}properties/")
ENERSTAT = Namespace(f"{CONSUMPTION}statistics/")
ENERVOC = Namespace(f"{CONSUMPTION}vocab/")

MEASURES = {
    'heating': {
        'column': "Verbrauch Wärme (witterungsbereinigt)  {year} [kWh/a]",
        'property': ENERVOC.heatingConsumption,
        'label': {
            'de': "Energieverbrauch Wärme",
            'en': "Energy consumption heating"
        }
    },
    'power': {
        'column': "Strom {year} [kWh/a]",
        'property': ENERVOC.powerConsumption,
        'label': {
            'de': "Energieverbrauch Strom",
            'en': "Energy consumption power"
        }
    },
    'co2': {
        'column': "CO2-Emissionen (Gesamt) {year} [t/a]",
        'property': ENERVOC.co2Emission,
        'label': {
            'de': "CO2-Emissionen",
            'en': "CO2 emissions"
        }
    }
}

HEATING_TYPES = {
    "Gas, Ölheizung": [ ENERVOC['gasHeating'], ENERVOC['oilHeating'] ],
    "Fernwärme": [ ENERVOC['districtHeating'] ],
    "Gas": [ ENERVOC['gasHeating'] ],
    "Nahwärme": [ ENERVOC['localHeating'] ],
    "Speicherheizung": [ ENERVOC['storageHeating'] ],
    "Strom (WP)": [ ENERVOC['heatPump'] ],
    "Stromheizung (kein Speicher)": [ENERVOC['directHeater'] ],
    "keine Angabe": [],
    "Ölheizung": [ ENERVOC['oilHeating'] ],
}

# we generate building ids from their names, but the names aren't unique
# this means we need to keep track of the ids we generate
BUILDING_IDS = []

def create_unique_id(base_id: str, haystack: list) -> str:
    """Return the `base_id` with an index number attached to
    ensure it is unique within `haystack`.

    Args:
        base_id (str): the base id to make unique by attaching an index
        haystack (list): the list of ids to check against

    Returns:
        str: `base_id` (if unique) or `base_id_{index}`
    """
    if base_id not in haystack:
        haystack.append(base_id)
        return base_id

    index = 1
    while f"{base_id}_{index}" in haystack:
        index += 1

    result = f"{base_id}_{index}"
    haystack.append(result)
    return result

def convert_row_no_vocab(row: dict, graph: Graph):
    """Convert a row of input CSV to an RDF graph, using only basic URIs on the 
    base URI of the target graph.

    Args:
        row (dict): a row of the input file as a dict
        graph (Graph): the output RDF graph
    """
    LOG.info(f" reading {row[ROW_ID]} – {row[ROW_BUILDING]}")

    # create building resource
    building_id = slugify(row[ROW_BUILDING])
    building_res = URIRef(building_id)

    # link basic building properties
    graph.add( (building_res, URIRef('name'), Literal(row[ROW_BUILDING])) )
    graph.add( (building_res, URIRef('comment'), Literal(row[ROW_COMMENT])) )
    graph.add( (building_res, URIRef('floor_area'), Literal(row[ROW_FLOOR_AREA], datatype=XSD.integer)) )

    # create heating type resource and link to building
    heating_type_id = slugify(row[ROW_HEATING_TYPE])
    heating_type_res = URIRef(heating_type_id)
    graph.add( (building_res, URIRef('heating_type'), heating_type_res) )

    # create address resource and link to building
    address_res = BNode()
    graph.add( (address_res, URIRef('street'), Literal(row[ROW_STREET])) )
    graph.add( (address_res, URIRef('zip_code'), Literal(row[ROW_ZIP])) )
    graph.add( (address_res, URIRef('location'), Literal(row[ROW_LOCATION])) )
    graph.add( (building_res, URIRef('address'), address_res) )

    # creating statistical observations for each year from 2019-2023
    start_year = 2019
    end_year = 2023

    # for each year
    for year in list(range(start_year, end_year+1)):
        LOG.info(f" creating observations for {year}")

        # for each dimension
        for dimension, pattern in MEASURES.items():
            # create resource for observation
            obs_id = f"{building_id}-{year}-{dimension}"
            obs_res = URIRef(f"obs_{obs_id}")

            # link to dimensions
            graph.add( (obs_res, URIRef('building'), building_res) )
            graph.add( (obs_res, URIRef('year'), Literal(year, datatype=XSD.integer)) )
            value = row[pattern.format(year=year)]
            graph.add( (obs_res, MEASURE_PROPERTIES[dimension], Literal(value, datatype=XSD.integer)) )

def convert_row_with_vocab(row: dict, graph: Graph, cube_res: URIRef):
    """Convert a row of input CSV to an RDF graph, using standard and custom
    vocabularies.

    Args:
        row (dict): a row of the input file as a dict
        graph (Graph): the output RDF graph
    """
    LOG.info(f" reading {row[ROW_ID]} – {row[ROW_BUILDING]}")

    # create building resource
    building_id = create_unique_id(slugify(row[ROW_BUILDING]), BUILDING_IDS)
    building_res = ENERPROP[building_id]

    # link basic building properties
    graph.add( (building_res, RDF.type, ENERVOC.Property) )
    graph.add( (building_res, RDFS.label, Literal(row[ROW_BUILDING])) )
    comment = row[ROW_COMMENT]
    if comment != "keine":
        graph.add( (building_res, RDFS.comment, Literal(row[ROW_COMMENT])) )
    graph.add( (building_res, ENERVOC.hasFloorArea, Literal(row[ROW_FLOOR_AREA], datatype=XSD.integer)) )

    # create heating type resource and link to building
    for heating_type in HEATING_TYPES[row[ROW_HEATING_TYPE]]:
        graph.add( (building_res, ENERVOC.hasHeatingType, heating_type) )

    # create address resource and link to building
    address_res = BNode()
    graph.add( (address_res, RDF.type, VCARD['Address']) )
    graph.add( (address_res, VCARD['street-address'], Literal(row[ROW_STREET])) )
    graph.add( (address_res, VCARD['postal-code'], Literal(row[ROW_ZIP])) )
    graph.add( (address_res, VCARD['locality'], Literal(row[ROW_LOCATION])) )
    graph.add( (building_res, VCARD['hasAddress'], address_res) )

    # creating statistical observations for each year from 2019-2023
    start_year = 2019
    end_year = 2023

    # create the cube object

    # for each year
    for year in list(range(start_year, end_year+1)):
        LOG.info(f" creating observations for {year}")

        # for each dimension
        for key, dimension in MEASURES.items():

            # create resource for observation set (we are grouping all 
            # observations with the same dimension+year in one set)
            set_id = f"{year}-{key}"
            set_res = ENERSTAT[f"os_{set_id}"]

            graph.add( (set_res, RDF.type, CUBE.ObservationSet) )
            graph.add( (set_res, RDFS.label, Literal(f"Observations for {key} in {year}", lang="en")) )
            graph.add( (set_res, RDFS.label, Literal(f"Beobachtungen von {key} in {year}", lang="de")) )
            graph.add( (cube_res, CUBE.observationSet, set_res) )

            # create resource for observation
            obs_id = f"{building_id}-{year}-{key}"
            obs_res = ENERSTAT[f"obs_{obs_id}"]

            graph.add( (obs_res, RDF.type, CUBE.Observation) )
            graph.add( (set_res, CUBE.observation, obs_res) )

            # link to dimensions
            graph.add( (obs_res, ENERVOC.property, building_res) )
            graph.add( (obs_res, DCTERMS.date, Literal(year, datatype=XSD.year)) )
            value = row[dimension['column'].format(year=year)]
            graph.add( (obs_res, dimension['property'], Literal(value, datatype=XSD.integer)) )



logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

DEFAULT_INPUT_PATH = os.path.join('data', 'source', 'input.csv')
DEFAULT_OUTPUT_PATH = os.path.join('data', 'target', 'output.ttl')

parser = argparse.ArgumentParser(
    description="Convert input csv to rdf.")
parser.add_argument('--input',
                    help=f"Path to input CSV. Default: {DEFAULT_INPUT_PATH}",
                    default=DEFAULT_INPUT_PATH,
                    )
parser.add_argument('--output',
                    help=f"Path to output TTL. Default: {DEFAULT_OUTPUT_PATH}",
                    default=DEFAULT_OUTPUT_PATH,
                    )

args = parser.parse_args()

graph = Graph()
cube_res = ENERSTAT.cube
graph.add( (cube_res, RDF.type, CUBE.Cube) )
graph.add( (cube_res, SCHEMA.name, Literal("Energy consumption Tempelhof-Schöneberg", lang='en')))
graph.add( (cube_res, SCHEMA.name, Literal("Energieverbrauch Tempelhof-Schöneberg", lang='de')))
graph.add( (cube_res, SCHEMA.description, Literal("""Data cube containing statistical
                                                  data about energy consumption in Berlin's
                                                  district of Tempelhof-Schöneberg.""", lang='en')))
graph.add( (cube_res, SCHEMA.description, Literal("""Data Cube mit statistischen Daten zum Energieverbrauch
                                                  öffentlicher Liegenschaften im Berliner Bezirk
                                                  Tempelhof-Schöneberg.""", lang='de')))

with_vocabs = True
LOG.info(f" opening input CSV: '{args.input}'")
if with_vocabs:
    graph.bind("enerprop", ENERPROP)
    graph.bind("cube", CUBE)
    graph.bind("enervoc", ENERVOC)
    graph.bind("enerstat", ENERSTAT)
    graph.bind("vcard", VCARD)
with open(args.input) as input_csv:
    reader = csv.DictReader(input_csv)
    for row in reader:
        if with_vocabs:
            convert_row_with_vocab(row, graph, cube_res)
        else:
            convert_row_no_vocab(row, graph)

print(graph.serialize(format="turtle"))
