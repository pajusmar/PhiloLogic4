#!/usr/bin/env python

import requests
import sys
from optparse import OptionParser, BadOptionError, AmbiguousOptionError
from json import dump


class PhiloLogicRequest(object):
    """
    Process a PhiloLogic request and save the full result set in a text file
    in JSON or tab delimited
    """
    
    def __init__(self, db_url=None, report=None, export_format="json", **args):
        self.db_url = db_url
        self.report = report
        self.export_format = export_format.lower()
        self.philo_args = args
        self.query_params = {"format": "json"}  ## Hardcoded to JSON since no other export function is currently available
        self.query_params["report"] = report
        self.query_params.update(args)
        if "method" not in self.query_params:
            self.query_params["method"] = "proxy"
        if "results_per_page" not in self.query_params:
            self.query_params["results_per_page"] = 5000
        if "q" not in self.query_params:
            self.query_params["q"] = ''
        self.total_hits()
        print >> sys.stderr, "Total hits:", self.total
        
        ## Count number of queries needed to retrieve the full result set
        if report == "concordance" or report == "kwic":
            self.interval = self.query_params["results_per_page"]
        else:
            self.interval = 5000
        self.steps = self.total / self.interval
        remainder = self.total % self.interval
        if remainder:
            self.steps += 1
        print >> sys.stderr, "%d queries in batches of %d hits will be performed to retrieve the full result set" % (self.steps, self.interval)
            
    def total_hits(self):
        r = requests.get(self.db_url + "/scripts/get_total_results.py", params=self.query_params)
        try:
            self.total = int(r.json())
        except ValueError:
            print >> sys.stderr, "Invalid URL:"
            print >> sys.stderr, r.url
            exit()
    
    def query(self, params=None):
        if params == None:
            params = self.query_params
        response = requests.get(self.db_url + "/dispatcher.py", params=params)
        return response
    
    def build_result_set(self):
        if self.report == "concordance" or self.report == "kwic":
            self.concatenate_concordance()
        elif self.report == "collocation":
            self.concatenate_collocation()
        elif self.report == "time_series":
            self.concatenate_time_series()
    
    def concatenate_concordance(self):
        params = dict(self.query_params)
        self.results = {"results": []}
        for i in range(self.steps):
            start = i * self.interval
            end = start + self.interval - 1
            params["start"] = start
            params["end"] = end
            response = self.query(params=params)
            print >> sys.stderr, "Done retrieving %s..." % response.url
            for k, v in response.json().iteritems():
                if k == "results":
                    self.results["results"] += v
                    continue
                if k not in self.results:
                    self.results[k] = v
        self.results["query"]["end"] = str(self.total - 1)
                    
    def concatenate_collocation(self):
        params = dict(self.query_params)
        params["start"] = 0
        params["end"] = self.interval
        self.results = {}
        for i in range(self.steps):
            start = i * self.interval
            end = start + self.interval - 1
            params["start"] = start
            params["end"] = end
            response = self.query(params=params)
            print >> sys.stderr, "Done retrieving %s..." % response.url
            results_object = response.json()
            if not self.results:
                self.results = results_object
            else:
                for word, word_obj in results_object["all_collocates"].iteritems():
                    if word in self.results["all_collocates"]:
                        self.results["all_collocates"][word]['count'] += word_obj['count']
                    else:
                        self.results["all_collocates"][word] = word_obj
                for word, word_obj in results_object["right_collocates"].iteritems():
                    if word in self.results["right_collocates"]:
                        self.results["right_collocates"][word]['count'] += word_obj['count']
                    else:
                        self.results["right_collocates"][word] = word_obj
                for word, word_obj in results_object["left_collocates"].iteritems():
                    if word in self.results["left_collocates"]:
                        self.results["left_collocates"][word]['count'] += word_obj['count']
                    else:
                        self.results["left_collocates"][word] = word_obj
        self.results["all_collocates"] = sorted(self.results["all_collocates"].iteritems(), key=lambda x: x[1], reverse=True)
        self.results["right_collocates"] = sorted(self.results["right_collocates"].iteritems(), key=lambda x: x[1], reverse=True)
        self.results["left_collocates"] = sorted(self.results["left_collocates"].iteritems(), key=lambda x: x[1], reverse=True)
        
    def concatenate_time_series(self):
        params = dict(self.query_params)
        if "year_interval" not in params:
            params["year_interval"] = "10"
        params["start"] = 0
        params["end"] = self.interval
        self.results = {}
        for i in range(self.steps):
            start = i * self.interval
            end = start + self.interval - 1
            params["start"] = start
            params["end"] = end
            response = self.query(params=params)
            print >> sys.stderr, "Done retrieving %s..." % response.url
            results_object = response.json()
            if not self.results:
                self.results = results_object
            else:
                for year, count in results_object['results']['absolute_count'].iteritems():
                    if year in self.results['results']["absolute_count"]:
                        self.results['results']["absolute_count"][year] += count
                    else:
                        self.results['results']["absolute_count"][year] = count
                for year, count in results_object['results']['date_count'].iteritems():
                    if year not in self.results['results']["date_count"]:
                        self.results['results']["date_count"][year] = count
        self.results['results']["absolute_count"] = sorted(self.results['results']['absolute_count'].iteritems(), key=lambda x: x[0])
        self.results['results']["date_count"] = sorted(self.results['results']['date_count'].iteritems(), key=lambda x: x[0])
    
    def save_file(self):
        if self.export_format == "json":
            filename = "%s_results.json" % self.report
            output_file = open(filename, 'w')
            dump(self.results, output_file, indent=2)
        elif self.export_format == "tab":
            print >> sys.stderr, "TAB export not implemented yet, try JSON output"
            exit()

class PassThroughOptionParser(OptionParser):
    """
    An unknown option pass-through implementation of OptionParser.

    When unknown arguments are encountered, bundle with largs and try again,
    until rargs is depleted.  

    sys.exit(status) will still be called if a known argument is passed
    incorrectly (e.g. missing arguments or bad argument types, etc.)        
    """
    def _process_args(self, largs, rargs, values):
        while rargs:
            try:
                OptionParser._process_args(self,largs,rargs,values)
            except (BadOptionError,AmbiguousOptionError), e:
                largs.append(e.opt_str)

def parse_command_line(arguments):
    parser = PassThroughOptionParser()
    parser.add_option("-r", "--report", action="store", default="concordance", type="string", dest="report", help="select PhiloLogic search report")
    parser.add_option("-d", "--db-url", action="store", default="", type="string", dest="db_url", help="select database URL for search")
    parser.add_option("-e", "--export-format", action="store", default="", type="string", dest="export_format", help="select output format. Options are JSON or TAB.")
    
    ## Parse command-line arguments
    options, args = parser.parse_args(arguments)
    
    ## Parse all other options
    arg_dict = {}
    while args:
        key = args.pop(0).replace('-', '')
        val = args.pop(0)
        arg_dict[key] = val.decode('utf-8')
        
    if not options.export_format:
        print >> sys.stderr, "No export format select, exporting to JSON..."
        export_format = "json"
    else:
        export_format = options.export_format
    
    return options.db_url, options.report, export_format, arg_dict 


if __name__ == '__main__':
    db_url, report, export_format, query_args = parse_command_line(sys.argv[1:])
    philo_request = PhiloLogicRequest(report=report, db_url=db_url, export_format=export_format, **query_args)
    philo_request.build_result_set()
    philo_request.save_file()