#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import os,sys,traceback
import re,shutil

from pyramid.view import view_config, view_defaults
from pyramid.response import FileResponse

import logging
from pprint import pformat
import textwrap
import datetime

from pygments import highlight
from pygments.lexers import TurtleLexer
from pygments.formatters import HtmlFormatter

from askomics.libaskomics.ParamManager import ParamManager
from askomics.libaskomics.ModulesManager import ModulesManager
from askomics.libaskomics.TripleStoreExplorer import TripleStoreExplorer
from askomics.libaskomics.SourceFileConvertor import SourceFileConvertor
from askomics.libaskomics.rdfdb.SparqlQueryBuilder import SparqlQueryBuilder
from askomics.libaskomics.rdfdb.SparqlQueryGraph import SparqlQueryGraph
from askomics.libaskomics.rdfdb.SparqlQueryStats import SparqlQueryStats
from askomics.libaskomics.rdfdb.SparqlQueryAuth import SparqlQueryAuth
from askomics.libaskomics.rdfdb.QueryLauncher import QueryLauncher
from askomics.libaskomics.source_file.SourceFile import SourceFile

from pyramid.httpexceptions import (
    HTTPForbidden,
    HTTPFound,
    HTTPNotFound,
    )

from validate_email import validate_email

from askomics.libaskomics.Security import Security

@view_defaults(renderer='json', route_name='start_point')
class AskView(object):
    """ This class contains method calling the libaskomics functions using parameters from the js web interface (body variable) """

    def __init__(self, request):
        # Manage solution/data/error inside. This object is return to client side
        self.data = {}
        self.log = logging.getLogger(__name__)
        self.request = request
        self.settings = request.registry.settings
        self.log.debug("==============================================================")
        self.log.debug(self.request.session)
        self.log.debug("==============================================================")
        try:

            if 'admin' not in self.request.session.keys():
                self.request.session['admin'] = False

            if 'blocked' not in self.request.session.keys():
                self.request.session['blocked'] = True

            if 'group' not in self.request.session.keys():
                self.request.session['group'] = ''

            if 'username' not in self.request.session.keys():
                self.request.session['username'] = ''

        except Exception as e:
                traceback.print_exc(file=sys.stdout)
                self.data['error'] = str(e)
                self.log.error(str(e))

    def check_error(self):
        if 'error' in self.data :
            return True
        return False

    def setGraphUser(self,removeGraph=[]):

        self.settings['graph'] = {}

        #finding all private graph graph
        sqg = SparqlQueryGraph(self.settings, self.request.session)
        ql = QueryLauncher(self.settings, self.request.session)

        results = ql.process_query(sqg.get_user_graph_infos().query)
        self.settings['graph']['private'] = []
        for elt in results:
            if 'g' not in elt:
                continue
            if elt['g'] in removeGraph:
                continue
            self.settings['graph']['private'].append(elt['g'])

        #finding all public graph
        results = ql.process_query(sqg.get_public_graphs().query)
        self.settings['graph']['public'] = []
        for elt in results:
            if elt['g'] in removeGraph:
                continue
            self.settings['graph']['public'].append(elt['g'])

    @view_config(route_name='start_point', request_method='GET')
    def start_points(self):
        """ Get the nodes being query starters """
        self.log.debug("== START POINT ==")

        if self.check_error():
            return self.data

        self.setGraphUser([])

        tse = TripleStoreExplorer(self.settings, self.request.session)
        nodes = tse.get_start_points()

        self.data['nodes'] = {}

        for node in nodes:
            if node['uri'] in self.data['nodes'].keys():
                if node['public'] and not self.data['nodes'][node['uri']]['public']:
                    self.data['nodes'][node['uri']]['public'] = True
                if node['private'] and not self.data['nodes'][node['uri']]['private']:
                    self.data['nodes'][node['uri']]['private'] = True
                self.data['nodes'][node['uri']]['public_and_private'] = bool(
                    self.data['nodes'][node['uri']]['public'] and
                    self.data['nodes'][node['uri']]['private'])
            else:
                self.data['nodes'][node['uri']] = node

        return self.data


    @view_config(route_name='statistics', request_method='GET')
    def statistics(self):
        """
        Get stats
        """
        # Denny access for non loged users
        if self.request.session['username'] == '':
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'

        self.log.debug('=== stats ===')

        self.data['username'] = self.request.session['username']

        sqs = SparqlQueryStats(self.settings, self.request.session)
        qlaucher = QueryLauncher(self.settings, self.request.session)

        public_stats = {}
        private_stats = {}

        # Number of triples
        results_pub = qlaucher.process_query(sqs.get_number_of_triples('public').query)
        results_priv = qlaucher.process_query(sqs.get_number_of_triples('private').query)

        public_stats['ntriples'] = results_pub[0]['number']
        private_stats['ntriples'] = results_priv[0]['number']

        # Number of entities
        results_pub = qlaucher.process_query(sqs.get_number_of_entities('public').query)
        results_priv = qlaucher.process_query(sqs.get_number_of_entities('private').query)

        public_stats['nentities'] = results_pub[0]['number']
        private_stats['nentities'] = results_priv[0]['number']

        # Number of classes
        results_pub = qlaucher.process_query(sqs.get_number_of_classes('public').query)
        results_priv = qlaucher.process_query(sqs.get_number_of_classes('private').query)

        public_stats['nclasses'] = results_pub[0]['number']
        private_stats['nclasses'] = results_priv[0]['number']

        # Number of graphs
        results_pub = qlaucher.process_query(sqs.get_number_of_subgraph('public').query)
        results_priv = qlaucher.process_query(sqs.get_number_of_subgraph('private').query)

        public_stats['ngraphs'] = results_pub[0]['number']
        private_stats['ngraphs'] = results_priv[0]['number']

        # Graphs info
        results_pub = qlaucher.process_query(sqs.get_subgraph_infos('public').query)
        results_priv = qlaucher.process_query(sqs.get_subgraph_infos('private').query)

        public_stats['graphs'] = results_pub
        private_stats['graphs'] = results_priv

        # Classes and relations
        results_pub = qlaucher.process_query(sqs.get_rel_of_classes('public').query)
        results_priv = qlaucher.process_query(sqs.get_rel_of_classes('private').query)

        public_stats['class_rel'] = results_pub
        private_stats['class_rel'] = results_priv

        tmp = {}

        for result in results_pub:
            if result['domain'] not in tmp.keys():
                tmp[result['domain']] = []
            if result['relname'] not in tmp[result['domain']]:
                tmp[result['domain']].append({'relname': result['relname'], 'target': result['range']})
        public_stats['class_rel'] = tmp

        tmp = {}

        for result in results_priv:
            if result['domain'] not in tmp.keys():
                tmp[result['domain']] = []
            if result['relname'] not in tmp[result['domain']]:
                tmp[result['domain']].append({'relname': result['relname'], 'target': result['range']})
        private_stats['class_rel'] = tmp

        # class and attributes
        results_pub = qlaucher.process_query(sqs.get_attr_of_classes('public').query)
        results_priv = qlaucher.process_query(sqs.get_attr_of_classes('private').query)

        tmp = {}

        for result in results_pub:
            if result['class'] not in tmp.keys():
                tmp[result['class']] = []
            if result['attr'] not in tmp[result['class']]:
                tmp[result['class']].append(result['attr'])
        public_stats['class_attr'] = tmp

        tmp = {}

        for result in results_priv:
            if result['class'] not in tmp.keys():
                tmp[result['class']] = []
            if result['attr'] not in tmp[result['class']]:
                tmp[result['class']].append(result['attr'])
        private_stats['class_attr'] = tmp

        self.data['public'] = public_stats
        self.data['private'] = private_stats

        return self.data

    @view_config(route_name='empty_user_database', request_method='GET')
    def empty_database(self):
        """
        Delete all named graphs and their metadatas
        """

        # Denny access for non loged users
        if self.request.session['username'] == '':
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'

        self.log.debug("=== DELETE ALL NAMED GRAPHS ===")

        try:
            sqb = SparqlQueryBuilder(self.settings, self.request.session)
            ql = QueryLauncher(self.settings, self.request.session)

            named_graphs = self.list_user_graph()

            for graph in named_graphs:

                self.log.debug("--- DELETE GRAPH : %s", graph['g'])
                ql.execute_query(sqb.get_drop_named_graph(graph['g']).query)
                #delete metadatas
                ql.execute_query(sqb.get_delete_metadatas_of_graph(graph['g']).query)

        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            self.data['error'] = str(e)
            self.log.error(str(e))

        return self.data

    @view_config(route_name='delete_graph', request_method='POST')
    def delete_graph(self):
        """
        Delete selected named graphs and their metadatas
        """

        # Denny access for non loged users
        if self.request.session['username'] == '':
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'

        sqb = SparqlQueryBuilder(self.settings, self.request.session)
        ql = QueryLauncher(self.settings, self.request.session)

        graphs = self.request.json_body['named_graph']

        #TODO: check if the graph belong to user

        for graph in graphs:
            self.log.debug("--- DELETE GRAPH : %s", graph)
            ql.execute_query(sqb.get_drop_named_graph(graph).query)
            #delete metadatas
            ql.execute_query(sqb.get_delete_metadatas_of_graph(graph).query)

    @view_config(route_name='list_user_graph', request_method='GET')
    def list_user_graph(self):
        """
        Return a list with all the named graphs of a user.
        """

        # Denny access for non loged users
        if self.request.session['username'] == '':
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'

        sqg = SparqlQueryGraph(self.settings, self.request.session)
        query_launcher = QueryLauncher(self.settings, self.request.session)

        res = query_launcher.execute_query(sqg.get_user_graph_infos().query)

        named_graphs = []

        for index_result in range(len(res['results']['bindings'])):

            dat = datetime.datetime.strptime(res['results']['bindings'][index_result]['date']['value'], "%Y-%m-%dT%H:%M:%S.%f")
            self.log.debug(dat)

            readable_date = dat.strftime("%y-%m-%d at %H:%M:%S")

            named_graphs.append({
                'g': res['results']['bindings'][index_result]['g']['value'],
                'name': res['results']['bindings'][index_result]['name']['value'],
                'count': res['results']['bindings'][index_result]['co']['value'],
                'date': res['results']['bindings'][index_result]['date']['value'],
                'readable_date': readable_date,
                'access': res['results']['bindings'][index_result]['access']['value'],
                'access_bool': bool(res['results']['bindings'][index_result]['access']['value'] == 'public')
            })

        return named_graphs

    @view_config(route_name='guess_csv_header_type', request_method='POST')
    def guess_csv_header_type(self):
        """Guess the headers type of a csv file

        Used for the asko-cli scripts

        :returns: list of guessed types
        :rtype: dict
        """

        # Denny access for non loged users
        if self.request.session['username'] == '':
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'

        body = self.request.json_body
        filename = body['filename']

        sfc = SourceFileConvertor(self.settings, self.request.session)
        source_file = sfc.get_source_file(filename)
        headers = source_file.headers
        preview = source_file.get_preview_data()

        guessed_types = []


        for index_header in range(0, len(headers)):
            guessed_types.append(source_file.guess_values_type(preview[index_header], headers[index_header]))

        self.data['types'] = guessed_types

        self.log.debug(self.data)
        return self.data




    @view_config(route_name='source_files_overview', request_method='GET')
    def source_files_overview(self):
        """
        Get preview data for all the available files
        """

        # Denny access for non loged users
        if self.request.session['username'] == '':
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'

        self.log.debug(" ========= Askview:source_files_overview =============")
        sfc = SourceFileConvertor(self.settings, self.request.session)

        source_files = sfc.get_source_files()

        self.data['files'] = []

        # get all taxon in the TS
        sqg = SparqlQueryGraph(self.settings, self.request.session)
        ql = QueryLauncher(self.settings, self.request.session)
        res = ql.execute_query(sqg.get_all_taxons().query)
        taxons_list = []
        for elem in res['results']['bindings']:
            taxons_list.append(elem['taxon']['value'])
        self.data['taxons'] = taxons_list

        for src_file in source_files:
            infos = {}
            infos['name'] = src_file.name
            infos['type'] = src_file.type
            if src_file.type == 'tsv':
                try:
                    infos['headers'] = src_file.get_headers_by_file
                    infos['preview_data'] = src_file.get_preview_data()
                    infos['column_types'] = []
                    header_num = 0
                    for ih in range(0, len(infos['headers'])):
                        #if infos['headers'][ih].find("@")>0:
                        #    infos['column_types'].append("entity")
                        #else:
                        infos['column_types'].append(src_file.guess_values_type(infos['preview_data'][ih], infos['headers'][header_num]))
                        header_num += 1
                except Exception as e:
                    traceback.print_exc(file=sys.stdout)
                    infos['error'] = 'Could not read input file, are you sure it is a valid tabular file?'
                    self.log.error(str(e))

                self.data['files'].append(infos)

            elif src_file.type == 'gff':
                try:
                    entities = src_file.get_entities()
                    infos['entities'] = entities
                except Exception as e:
                    self.log.debug('error !!')
                    traceback.print_exc(file=sys.stdout)
                    infos['error'] = 'Could not parse the file, are you sure it is a valid GFF3 file?'
                    self.log.error('error with gff examiner: ' + str(e))

                self.data['files'].append(infos)

            elif src_file.type == 'ttl':
                infos['preview'] = src_file.get_preview_ttl()
                self.data['files'].append(infos)


        return self.data


    @view_config(route_name='preview_ttl', request_method='POST')
    def preview_ttl(self):
        """
        Convert tabulated files to turtle according to the type of the columns set by the user
        """

        # Denny access for non loged users
        if self.request.session['username'] == '':
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'


        self.log.debug("preview_ttl")
        try:
            body = self.request.json_body
            file_name = body["file_name"]
            col_types = body["col_types"]
            disabled_columns = body["disabled_columns"]
            key_columns = body["key_columns"]

            sfc = SourceFileConvertor(self.settings, self.request.session)

            src_file = sfc.get_source_file(file_name)
            src_file.set_forced_column_types(col_types)
            src_file.set_disabled_columns(disabled_columns)
            src_file.set_key_columns(key_columns)

            cont_ttl = '\n'.join(src_file.get_turtle(preview_only=True))
            self.data = textwrap.dedent(
            """
            {header}

            #############
            #  Content  #
            #############

            {content_ttl}

            #################
            #  Abstraction  #
            #################

            {abstraction_ttl}

            ######################
            #  Domain knowledge  #
            ######################

            {domain_knowledge_ttl}
            """).format(header=sfc.get_turtle_template(cont_ttl),
                    content_ttl = cont_ttl,
                    abstraction_ttl = src_file.get_abstraction(),
                    domain_knowledge_ttl = src_file.get_domain_knowledge()
                    )
        except Exception as e:
            self.data['error'] = str(e)
            return self.data

        formatter = HtmlFormatter(cssclass='preview_field', nowrap=True, nobackground=True)
        return highlight(self.data, TurtleLexer(), formatter) # Formated html

    @view_config(route_name='load_data_into_graph', request_method='POST')
    def load_data_into_graph(self):
        """
        Load tabulated files to triple store according to the type of the columns set by the user
        """

        # Denny access for non loged users
        if self.request.session['username'] == '':
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'

        body = self.request.json_body
        file_name = body["file_name"]
        col_types = body["col_types"]
        disabled_columns = body["disabled_columns"]
        key_columns = body["key_columns"]
        public = body['public']
        headers = body['headers']
        uri = None
        if 'uri' in body:
            uri = body['uri']

        method = 'load'
        if 'method' in body:
            method = body['method']

        forced_type = None
        if 'forced_type' in body:
            forced_type = body['forced_type']

        # Allow data integration in public graph only if user is an admin
        if public and not self.request.session['admin']:
            self.data['error'] = ('/!\\ --> NOT ALLOWED TO INSERT IN PUBLIC GRAPH <-- /!\\')
            return self.data

        sfc = SourceFileConvertor(self.settings, self.request.session)
        src_file = sfc.get_source_file(file_name, forced_type, uri=uri)
        src_file.set_headers(headers)
        src_file.set_forced_column_types(col_types)
        src_file.set_disabled_columns(disabled_columns)
        src_file.set_key_columns(key_columns)

        try:
            self.data = src_file.persist(self.request.host_url, method, public)
        except Exception as e:
            #rollback
            sqb = SparqlQueryBuilder(self.settings, self.request.session)
            query_laucher = QueryLauncher(self.settings, self.request.session)
            query_laucher.execute_query(sqb.get_drop_named_graph(src_file.graph).query)
            query_laucher.execute_query(sqb.get_delete_metadatas_of_graph(src_file.graph).query)

            traceback.print_exc(file=sys.stdout)
            self.data['error'] = 'Probleme with user data file ?</br>'+str(e)
            self.log.error(str(e))

        return self.data

    @view_config(route_name='load_gff_into_graph', request_method='POST')
    def load_gff_into_graph(self):
        """
        Load GFF file into the triplestore
        """

        # Denny access for non loged users
        if self.request.session['username'] == '':
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'


        self.log.debug("== load_gff_into_graph ==")

        body = self.request.json_body
        self.log.debug('===> body: '+str(body))
        file_name = body['file_name']
        taxon = body['taxon']
        entities = body['entities']
        public = body['public']
        uri = None
        if 'uri' in body:
            uri = body['uri']

        method = 'load'
        if 'method' in body:
            method = body['method']

        forced_type = None
        if 'forced_type' in body:
            forced_type = body['forced_type']

        # Allow data integration in public graph only if user is an admin
        if public and not self.request.session['admin']:
            self.log.debug('/!\\ --> NOT ALLOWED TO INSERT IN PUBLIC GRAPH <-- /!\\')
            public = False

        sfc = SourceFileConvertor(self.settings, self.request.session)
        src_file_gff = sfc.get_source_file(file_name, forced_type, uri=uri)

        src_file_gff.set_taxon(taxon)
        src_file_gff.set_entities(entities)

        try:
            self.log.debug('--> Parsing GFF')
            src_file_gff.persist(self.request.host_url, method, public)
        except Exception as e:
            #rollback
            sqb = SparqlQueryBuilder(self.settings, self.request.session)
            query_laucher = QueryLauncher(self.settings, self.request.session)
            query_laucher.execute_query(sqb.get_drop_named_graph(src_file_gff.graph).query)
            query_laucher.execute_query(sqb.get_delete_metadatas_of_graph(src_file_gff.graph).query)

            traceback.print_exc(file=sys.stdout)
            self.data['error'] = 'Problem when integration of '+file_name+'.</br>'+str(e)
            self.log.error(str(e))

        self.data['status'] = 'ok'
        return self.data

    @view_config(route_name='load_ttl_into_graph', request_method='POST')
    def load_ttl_into_graph(self):
        """
        Load TTL file into the triplestore
        """

        # Denny access for non loged users
        if self.request.session['username'] == '':
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'


        self.log.debug('*** load_ttl_into_graph ***')

        body = self.request.json_body
        file_name = body['file_name']
        public = body['public']
        method = 'load'
        if 'method' in body:
            method = body['method']

        forced_type = None
        if 'forced_type' in body:
            forced_type = body['forced_type']

        # Allow data integration in public graph only if user is an admin
        if public and not self.request.session['admin']:
            self.log.debug('/!\\ --> NOT ALLOWED TO INSERT IN PUBLIC GRAPH <-- /!\\')
            public = False

        sfc = SourceFileConvertor(self.settings, self.request.session)
        src_file_ttl = sfc.get_source_file(file_name, forced_type)

        try:
            self.data = src_file_ttl.persist(self.request.host_url, public, method)

        except Exception as e:
            #rollback
            sqb = SparqlQueryBuilder(self.settings, self.request.session)
            query_laucher = QueryLauncher(self.settings, self.request.session)
            query_laucher.execute_query(sqb.get_drop_named_graph(src_file_ttl.graph).query)
            query_laucher.execute_query(sqb.get_delete_metadatas_of_graph(src_file_ttl.graph).query)

            self.data['error'] = 'Problem when integration of ' + file_name + '</br>' + str(e)
            self.log.error('ERROR: ' + str(e))

        self.data['status'] = 'ok'
        return self.data


    @view_config(route_name='getUserAbstraction', request_method='POST')
    def getUserAbstraction(self):
        """ Get the user asbtraction to manage relation inside javascript """
        self.log.debug("== getUserAbstraction ==")
        body = self.request.json_body

        service = ''
        if 'service' in body :
            service = body['service']

        tse = TripleStoreExplorer(self.settings, self.request.session)
        self.data.update(tse.getUserAbstraction(service))

        return self.data

    #TODO : this method is too generic. The build of RDF Shortucts should be here to avoid injection with bad intention...

    @view_config(route_name='importShortcut', request_method='POST')
    def importShortcut(self):
        """
        Import a shortcut definition into the triplestore
        """
        # Denny access for non loged users
        if self.request.session['username'] == '' or not self.request.session['admin'] :
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'

        self.log.debug('*** importShortcut ***')

        body = self.request.json_body
        sqb = SparqlQueryBuilder(self.settings, self.request.session)
        ql = QueryLauncher(self.settings, self.request.session)
        sparqlHeader = sqb.header_sparql_config("")

        try:
            sparqlHeader += body["prefix"]+"\n"
            ql.insert_data(body["shortcut_def"],'askomics:graph:shortcut',sparqlHeader);
        except Exception as e:
            #exc_type, exc_value, exc_traceback = sys.exc_info()
            #traceback.print_exc(limit=8)
            traceback.print_exc(file=sys.stdout)
            self.data['error'] = str(e)
            self.log.error(str(e))

        return self.data

    @view_config(route_name='deleteShortcut', request_method='POST')
    def deleteShortcut(self):
        """
        Delete a shortcut definition into the triplestore
        """
        # Denny access for non loged users
        if self.request.session['username'] == '' or not self.request.session['admin'] :
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'

        self.log.debug('*** importShortcut ***')

        body = self.request.json_body
        sqb = SparqlQueryBuilder(self.settings, self.request.session)
        ql = QueryLauncher(self.settings, self.request.session)

        try:
            query_string = sqb.header_sparql_config("")
            query_string += "\n"
            query_string += "DELETE {\n"
            query_string += "\tGRAPH "+ "<askomics:graph:shortcut>" +"\n"
            query_string += "\t\t{\n"
            query_string += "<"+body["shortcut"]+">" + " ?r ?a.\n"
            query_string += "\t\t}\n"
            query_string += "\t}\n"
            query_string += "WHERE{\n"
            query_string += "<"+body["shortcut"]+">" + " ?r ?a.\n"
            query_string += "\t}\n"

            res = ql.execute_query(query_string)
        except Exception as e:
            #exc_type, exc_value, exc_traceback = sys.exc_info()
            #traceback.print_exc(limit=8)
            traceback.print_exc(file=sys.stdout)
            self.data['error'] = str(e)
            self.log.error(str(e))

        return self.data

    @view_config(route_name='modules', request_method='POST')
    def modules(self):

        # Denny access for non loged users
        if not self.request.session['admin'] :
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'

        try:
            mm = ModulesManager(self.settings, self.request.session)
            self.data =  mm.getListModules()
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            self.data['error'] = str(e)
            self.log.error(str(e))

        return self.data

    @view_config(route_name='manage_module', request_method='POST')
    def manageModules(self):
        # Denny access for non loged users
        if not self.request.session['admin'] :
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'

        try:
            body = self.request.json_body
            mm = ModulesManager(self.settings, self.request.session)

            mm.manageModules(
                    self.request.host_url,
                    body['uri'],
                    body['name'],
                    bool(body['checked']))

        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            self.data['error'] = str(e)
            self.log.error(str(e))

        return self.data

    @view_config(route_name='sparqlquery', request_method='POST')
    def get_value(self):
        """ Build a request from a json whith the following contents :variates,constraintesRelations,constraintesFilters"""

        body = self.request.json_body

        if 'headers' in body:
            ordered_headers = body['headers']

        try:
            tse = TripleStoreExplorer(self.settings, self.request.session)
            lfrom = []
            if 'from' in body:
                lfrom = body['from']
            results, query = tse.build_sparql_query_from_json(lfrom, body["variates"], body["constraintesRelations"], True)

            #body["limit"]
            # Remove prefixes in the results table
            limit = int(body["limit"]) + 1
            if body["limit"] != -1 and limit < len(results):
                self.data['values'] = results[1:limit+1]
            else:
                self.data['values'] = results

            self.data['nrow'] = len(results)

            # Provide results file
            if (not 'nofile' in body) or body['nofile']:
                query_laucher = QueryLauncher(self.settings, self.request.session)
                self.data['file'] = query_laucher.format_results_csv(results, ordered_headers)

        except Exception as e:
            #exc_type, exc_value, exc_traceback = sys.exc_info()
            #traceback.print_exc(limit=8)
            traceback.print_exc(file=sys.stdout)
            self.data['values'] = ""
            self.data['file'] = ""
            self.data['error'] = str(e)
            self.log.error(str(e))

        return self.data

    @view_config(route_name='getSparqlQueryInTextFormat', request_method='POST')
    def getSparqlQueryInTextFormat(self):
        """ Build a request from a json whith the following contents :variates,constraintesRelations,constraintesFilters"""
        self.log.debug("== Attribute Value ==")

        try:
            tse = TripleStoreExplorer(self.settings, self.request.session)

            body = self.request.json_body
            lfrom = []
            if 'from' in body:
                lfrom = body['from']

            results,query = tse.build_sparql_query_from_json(lfrom,body["variates"],body["constraintesRelations"],-1,False)

            self.data['query'] = query
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            self.data['error'] = str(e)
            self.log.error(str(e))

        return self.data

    @view_config(route_name='ttl', request_method='GET')
    def uploadTtl(self):

        pm = ParamManager(self.settings, self.request.session)
        response = FileResponse(
            pm.getRdfDirectory()+self.request.matchdict['name'],
            content_type='text/turtle'
            )
        return response

    @view_config(route_name='csv', request_method='GET')
    def uploadCsv(self):

        pm = ParamManager(self.settings, self.request.session)

        response = FileResponse(
            pm.getUserResultsCsvDirectory()+self.request.matchdict['name'],
            content_type='text/csv'
            )
        return response


    @view_config(route_name='del_csv', request_method='GET')
    def deletCsv(self):

        pm = ParamManager(self.settings, self.request.session)
        os.remove(pm.getUserResultsCsvDirectory()+self.request.matchdict['name']),



    @view_config(route_name='signup', request_method='POST')
    def signup(self):
        body = self.request.json_body
        username = body['username']
        email = body['email']
        password = body['password']
        password2 = body['password2']

        self.log.debug('==== user info ====')
        self.log.debug('username: ' + username)
        self.log.debug('email: ' + email)



        try:
            security = Security(self.settings, self.request.session, username, email, password, password2)

            is_valid_email = security.check_email()
            are_passwords_identical = security.check_passwords()
            is_pw_enough_longer = security.check_password_length()
            is_username_already_exist = security.check_username_in_database()
            is_email_already_exist = security.check_email_in_database()

            self.data['error'] = []
            error = False

            if not is_valid_email:
                self.data['error'].append('Email is not valid')
                error = True

            if not are_passwords_identical:
                self.data['error'].append('Passwords are not identical')
                error = True

            if not is_pw_enough_longer:
                self.data['error'].append('Password must be at least 8 characters')
                error = True

            if is_username_already_exist:
                self.data['error'].append('Username already exist')
                error = True

            if is_email_already_exist:
                self.data['error'].append('Email already exist')
                error = True

            if error:
                return self.data

            self.data['error'] = []

            security.persist_user(self.request.host_url)
            security.create_user_graph()
            security.log_user(self.request)

            self.data['username'] = username
            admin_blocked = security.get_admin_blocked_by_username()
            self.data['admin'] = admin_blocked['admin']
            self.data['blocked'] = admin_blocked['blocked']
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            self.data['error'] = ["Bad server configuration!"]
            self.log.error(str(e))

        return self.data

    @view_config(route_name='checkuser', request_method='GET')
    def checkuser(self):

        if self.request.session['username'] != '':
            self.data['username'] = self.request.session['username']
            self.data['admin'] = self.request.session['admin']
            self.data['blocked'] = self.request.session['blocked']

        return self.data


    @view_config(route_name='logout', request_method='GET')
    def logout(self):
        """
        Log out the user, reset the session
        """

        self.request.session['username'] = ''
        self.request.session['admin'] = ''
        self.request.session['graph'] = ''
        self.request.session = {}

        return

    @view_config(route_name='login', request_method='POST')
    def login(self):

        body = self.request.json_body
        username_email = body['username_email']
        password = body['password']
        username = ''
        email = ''

        self.data['error'] = []

        if validate_email(username_email):
            email = username_email
            auth_type = 'email'
        else:
            username = username_email
            auth_type = 'username'

        security = Security(self.settings, self.request.session, username, email, password, password)

        if auth_type == 'email':
            email_in_ts = security.check_email_in_database()

            if not email_in_ts:
                self.data['error'].append('email is not registered')
                return self.data

            password_is_correct = security.check_email_password()

            if not password_is_correct:
                self.data['error'].append('Password is incorrect')
                return self.data

            # Set username
            security.set_username_by_email()

            # Get the admin and blocked status
            admin_blocked = security.get_admin_blocked_by_email()
            security.set_admin(admin_blocked['admin'])
            security.set_blocked(admin_blocked['blocked'])


        elif auth_type == 'username':
            username_in_ts = security.check_username_in_database()

            if not username_in_ts:
                self.data['error'].append('username is not registered')
                return self.data

            # Get the admin and blocked status
            admin_blocked = security.get_admin_blocked_by_username()
            security.set_admin(admin_blocked['admin'])
            security.set_blocked(admin_blocked['blocked'])

            password_is_correct = security.check_username_password()

            if not password_is_correct:
                self.data['error'].append('Password is incorrect')
                return self.data

        # User pass the authentication, log him
        try:
            security.log_user(self.request)
            self.data['username'] = username
            self.data['admin'] = admin_blocked['admin']
            self.data['blocked'] = admin_blocked['blocked']

        except Exception as e:
            self.data['error'] = str(e)
            self.log.error(str(e))

        param_manager = ParamManager(self.settings, self.request.session)
        param_manager.getUploadDirectory()

        return self.data

    @view_config(route_name='api_key', request_method='POST')
    def api_key(self):

        # Denny access for non loged users or non admin users
        if self.request.session['username'] == '':
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'

        body = self.request.json_body
        self.log.debug(body)
        username = body['username']
        keyname = body['keyname']

        security = Security(self.settings, self.request.session, username, '', '', '')

        try:
            security.add_apikey(keyname)
            # query_laucher.process_query(sqa.add_apikey(username, keyname).query)
        except Exception as e:
            self.log.debug(str(e))
            self.data['error'] = str(e)
            return self.data

        self.data['sucess'] = 'success'
        return self.data

    @view_config(route_name='del_apikey', request_method='POST')
    def del_apikey(self):

        # Denny access for non loged users or non admin users
        if self.request.session['username'] == '':
            return 'forbidden'

        body = self.request.json_body
        key = body['key']

        security = Security(self.settings, self.request.session, self.request.session['username'], '', '', '')

        # Check the key belong to the user
        key_belong2user = security.ckeck_key_belong_user(key)

        if key_belong2user:
            security.delete_apikey(key)



    @view_config(route_name='login_api', request_method='POST')
    def login_api(self):

        body = self.request.json_body
        apikey = body['apikey']

        self.data['error'] = ''

        security = Security(self.settings, self.request.session, '', '', '', '')

        # Check if API key exist, and if yes, get the user
        security.get_owner_of_apikey(apikey)

        if not security.get_username():
            self.data['error'] = 'API key belong to nobody'
            return self.data

        # Get the admin and blocked status
        admin_blocked = security.get_admin_blocked_by_username()
        security.set_admin(admin_blocked['admin'])
        security.set_blocked(admin_blocked['blocked'])

        # Log the user
        try:
            security.log_user(self.request)
            self.data['username'] = security.get_username()
            self.data['admin'] = admin_blocked['admin']
            self.data['blocked'] = admin_blocked['blocked']

        except Exception as e:
            self.data['error'] = str(e)
            self.log.error(str(e))
            return self.data

        param_manager = ParamManager(self.settings, self.request.session)
        param_manager.getUploadDirectory()

        return self.data


    @view_config(route_name='get_users_infos', request_method='GET')
    def get_users_infos(self):
        """
        For each users store in the triplesore, get their username, email,
        and admin status
        """

        # Denny access for non loged users or non admin users
        if self.request.session['username'] == '' or not self.request.session['admin']:
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'

        sqa = SparqlQueryAuth(self.settings, self.request.session)
        ql = QueryLauncher(self.settings, self.request.session)

        try:
            result = ql.process_query(sqa.get_users_infos(self.request.session['username']).query)
        except Exception as e:
            self.data['error'] = str(e)
            self.log.error(str(e))

        for res in result:
            res['admin'] = ParamManager.Bool(res['admin'])
            res['blocked'] = ParamManager.Bool(res['blocked'])
            res['email'] = re.sub(r'^mailto:', '', res['email'])

        self.log.debug(result)

        self.data['result'] = result

        return self.data

    @view_config(route_name='lockUser', request_method='POST')
    def lock_user(self):
        """
        Change a user lock status
        """

        # Denny access for non loged users or non admin users
        if self.request.session['username'] == '' or not self.request.session['admin']:
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'

        body = self.request.json_body

        username = body['username']
        new_status = body['lock']

        # Convert bool to string for the triplestore
        if new_status:
            new_status = 'true'
        else:
            new_status = 'false'

        sqb = SparqlQueryBuilder(self.settings, self.request.session)
        query_laucher = QueryLauncher(self.settings, self.request.session)

        try:
            query_laucher.process_query(sqb.update_blocked_status(new_status, username).query)
        except Exception as e:
            return 'failed: ' + str(e)


        return 'success'

    @view_config(route_name='setAdmin', request_method='POST')
    def set_admin(self):
        """
        Change a user admin status
        """

        # Denny access for non loged users or non admin users
        if self.request.session['username'] == '' or not self.request.session['admin']:
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'

        body = self.request.json_body

        username = body['username']
        new_status = body['admin']

        # Convert bool to string for the triplestore
        if new_status:
            new_status = 'true'
        else:
            new_status = 'false'

        sqb = SparqlQueryBuilder(self.settings, self.request.session)
        query_laucher = QueryLauncher(self.settings, self.request.session)

        try:
            query_laucher.process_query(sqb.update_admin_status(new_status, username).query)
        except Exception as e:
            return 'failed: ' + str(e)


        return 'success'


    @view_config(route_name='delete_user', request_method='POST')
    def delete_user(self):
        """
        Delete a user from the user graphs, and remove all his data
        """

        # Denny access for non loged users
        if self.request.session['username'] == '':
            return 'forbidden'

        # Denny for blocked users
        if self.request.session['blocked']:
            return 'blocked'

        body = self.request.json_body

        username = body['username']
        passwd = body['passwd']
        confirmation = body['passwd_conf']

        # Non admin can only delete himself
        if self.request.session['username'] != username and not self.request.session['admin']:
            return 'forbidden'

        # If confirmation, check the user passwd
        if confirmation:
            security = Security(self.settings, self.request.session, username, '', passwd, passwd)
            if not security.check_username_password():
                self.data['error'] = 'Wrong password'
                return self.data


        sqb = SparqlQueryBuilder(self.settings, self.request.session)
        query_laucher = QueryLauncher(self.settings, self.request.session)

        # Get all graph of a user
        res = query_laucher.process_query(sqb.get_graph_of_user(username).query)

        list_graph = []
        for graph in res:
            list_graph.append(graph['g'])

        # Drop all this graph
        for graph in list_graph:
            try:
                query_laucher.execute_query(sqb.get_drop_named_graph(graph).query)
                query_laucher.execute_query(sqb.get_delete_metadatas_of_graph(graph).query)
            except Exception as e:
                return 'failed: ' + str(e)


        # Delete user infos
        try:
            query_laucher.execute_query(sqb.delete_user(username).query)
        except Exception as e:
            return 'failed: ' + str(e)

        # Is user delete himself, delog him
        if self.request.session['username'] == username:
            self.request.session['username'] = ''
            self.request.session['admin'] = ''
            self.request.session['graph'] = ''

        return 'success'

    @view_config(route_name='get_my_infos', request_method='GET')
    def get_my_infos(self):
        """
        Get all infos about a user
        """


        sqa = SparqlQueryAuth(self.settings, self.request.session)
        query_laucher = QueryLauncher(self.settings, self.request.session)

        try:
            result = query_laucher.process_query(sqa.get_user_infos(self.request.session['username']).query)
        except Exception as e:
            return 'failed: ' + str(e)


        apikey_list = []

        for res in result:
            if 'keyname' in res:
                self.log.debug(res['keyname'])
                self.log.debug(res['apikey'])
                # apikey_dict[res['keyname']] = res['apikey']
                apikey_list.append({'name': res['keyname'], 'key': res['apikey']})

        result = result[0]
        result['email'] = re.sub(r'^mailto:', '', result['email'])
        result['username'] = self.request.session['username']
        result['admin'] = ParamManager.Bool(result['admin'])
        result['blocked'] = ParamManager.Bool(result['blocked'])
        result.pop('keyname', None)
        result.pop('apikey', None)

        result['apikeys'] = apikey_list

        return result
    @view_config(route_name='update_mail', request_method='POST')
    def update_mail(self):
        """
        Chage email of a user
        """

        body = self.request.json_body
        username = body['username']
        email = body['email']

        # Check email

        security = Security(self.settings, self.request.session, username, email, '', '')

        if not security.check_email():
            self.data['error'] = 'Not a valid email'
            return self.data

        try:
            security.update_email()
        except Exception as e:
            self.data['error'] = 'error when updating mail: ' + str(e)
            return self.data

        self.data['success'] = 'success'

        return self.data

    @view_config(route_name='update_passwd', request_method='POST')
    def update_passwd(self):
        """
        Chage email of a user
        """

        body = self.request.json_body
        username = body['username']
        passwd = body['passwd']
        passwd2 = body['passwd2']
        current_passwd = body['current_passwd']

        security1 = Security(self.settings, self.request.session, username, '', current_passwd, current_passwd)

        if not security1.check_username_password():
            self.data['error'] = 'Current password is wrong'
            return self.data

        security = Security(self.settings, self.request.session, username, '', passwd, passwd2)


        # check if the passwd are identical
        if not security.check_passwords():
            self.data['error'] = 'Passwords are not identical'
            return self.data

        if not security.check_password_length():
            self.data['error'] = 'Password is too small (8char min)'
            return self.data


        try:
            security.update_passwd()
        except Exception as e:
            self.data['error'] = 'error when updating password: ' + str(e)
            return self.data

        self.data['success'] = 'success'

        return self.data
