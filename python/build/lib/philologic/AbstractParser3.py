from philologic.OHCOVector import *
import philologic.shlax as shlax
import re
import os
import philologic.Toms as Toms

class AbstractParser:
    def __init__(self,filename,docid): # should take object levels, mapping, metapaths as keyword arguments.
        self.reader = None
        self.writer = None
        self.filename = filename
        self.context = []
        self.counts = {}
        self.current_object = {} #goes
        self.meta_memory = {} #goes
        self.metahandler = None #goes?
        self.objects = OHCOVector(["doc","div1","div2","div3","para","sent","word"]) # the parser should know what its object levels are.
        self.objects.v[0] = docid # - 1 because we're about to increment it.
        self.full_did = self.objects.v
        self.objects_max = self.objects.v
        self.line_max = 0
        self.mapping = {# the raw mapping should be unambiguous, and context-free.                        
                        "front":"div",
                        "div":"div",
                        "div0":"div",
                        "div1":"div",
                        "div2":"div",
                        "div3":"div",
                        "p":"para",
                        "sp":"para",
                        "stage":"para"}
        self.metamap = { "titleStmt/author" : "author",
                         "titleStmt/title" : "title",
                         "div/head" : "head",
                         "div1/head" : "head"}
        self.metapaths = { "doc" : {"titleStmt/author" : "author", # metadata paths; order of evaluation is indeterminate, so MAKE SURE that they are unambiguous.
                            "titleStmt/title" : "title"},
                           "div" : {"head":"head"},
                           "para" : {"speaker": "who"}
                         }
        self.context_memory = {}
        self.parallel = {"line":0, #this should be implicit.
                         "byte":0} # this should be automatic.
        self.event_stream = None
        
    def parse(self, input, output):
        self.reader = input # filtering for bad encoding should be done in the reader
        self.writer = output # sorting or filtering output should be done by piping the writer
        self.event_stream = iter(shlax.parser(self.reader))
        # you need to iter() the parser so that it doesn't reset itself for each loop.
        self.object_stack = []
        self.meta_content_dest = [] 
        self.meta_attribute_dest = []
        self.make_object("TEI","doc",None,{"filename":self.filename})
        max_v = self.objects_max
        max_v.extend((self.parallel["byte"],self.line_max))
        return (max_v,self.counts)
            
    def make_object(self,name,type, first = None, attributes = {}):
        self.push_object(type)
        my_attributes = attributes.copy()
        my_attributes["start"] = first.start if first else self.parallel["byte"]
        my_id = self.objects.v[:]
        my_context = self.context[:]
        self.object_stack.append((name,type,my_id,my_context,my_attributes))
        for node in self.event_stream:
            self.parallel["byte"] = node.start

            if node.type == "StartTag":
                self.context.append(node.name)
                self.dispatch_metadata()
                # attribute dispatch is immediate; what if the child is a new object?
                if node.name in self.mapping:
                    newtype = self.mapping[node.name]
                    self.make_object(node.name,newtype,node)
                    # need to break on non-null returns and pass up to the parent.  tricky.
                if node.name == "l": #parallel objects are best handled with one-off hacks, in my opinion.
                    if "n" in node.attributes.keys():
                        self.parallel["line"] = int(node.attributes["n"])
                    else:
                        self.parallel["line"] += 1
                    print >> self.writer, "line %d %d" % (self.parallel["byte"],self.parallel["line"])
                    self.line_max = max(self.parallel["line"],self.line_max)

            elif node.type == "text":
                self.tokenize(node.content,node.start)

            elif node.type == "EndTag":
                self.cleanup_metadata()
                if len(self.context) and self.context[-1] == node.name:
                    # very conservative--this makes the stack tend to grow.
                    # you can wrap the lexer to auto-balance, if you wish.
                    self.context.pop()
                if node.name == name: 
                    # possibly too liberal here: could you have nested objects,
                    # with a child, having the same name, which does not itself emit an object?
                    my_attributes["end"] = node.start
                    break # this is key--the object will consume the whole document if you don't break at the right time.

        emit_object(self.writer,type,name, my_id,my_attributes["start"],self.parallel["line"],my_attributes)
        # note that objects are emitted in the order in which they END, due to the recursion. 
        # document finishes last. sort as necessary/desired.
        self.object_stack.pop()
        self.pull_object(type)

    def push_object(self,type):
        #should get merged into make_object
        self.objects.push(type)
        self.current_object[type] = self.objects.v[:]
        self.meta_memory[type] = self.context[:]
        self.objects_max = [max(x,y) for x,y in zip(self.objects.v,self.objects_max)]
        
    def dispatch_metadata(self):
        #why not do this in the object and text subroutines, respectively, since attrib and content dispatch is so different?
        for pattern in self.metamap:
            if context_match(self.context,pattern):
                self.metahandler = self.metamap[pattern]
                # TODO: use object_stack to send it to the right object

    def tokenize(self,text,offset):
        try: # long try blocks are bad...
            text = text.decode("utf-8")
            tokens = re.finditer(ur"([\w\u2019]+)|([\.;:?!])",text,re.U)
            # todo: name regex subgroups.
            meta_matched = False
            # may wish to sub out this loop, to use in attrib matching.
            for (parent_name,parent_type,parent_id,parent_context,parent_attributes) in reversed(self.object_stack):
                if self.context[:len(parent_context)] != parent_context: continue # this implies the file is damaged.  better to be safe.
                if parent_type not in self.metapaths: continue
                working_context = self.context[len(parent_context):]
                for path,destination in self.metapaths[parent_type].items():
                    if context_match(working_context,path):
                        parent_attributes[destination] = parent_attributes.get(destination,"") + re.sub("[\n\t]","",text.encode("utf-8"))
                        meta_matched = True
                if meta_matched: break
            if meta_matched: pass
            else:
				for token in tokens:
					if token.group(1):
						self.push_object("word")
						char_offset = token.start(1)
						byte_length = len(text[:char_offset].encode("utf-8"))
						emit_object(self.writer,"word",token.group(1),self.objects.v,offset + byte_length,self.parallel["line"])                           
						self.counts[token.group(1)] = self.counts.get(token.group(1),0) + 1
					if token.group(2):
						self.push_object("sent")
						char_offset = token.start(2)
						byte_length = len(text[:char_offset].encode("utf-8"))
						emit_object(self.writer,"sent",token.group(2),self.objects.v,offset + byte_length,self.parallel["line"])                           
        except UnicodeDecodeError as err:
            print >> sys.stderr, "%s : %s@%s : %s;%s" % (type(err),self.filename,offset,err,err.args)

    def cleanup_metadata(self):
    	# this should become unnecessary.
        for pattern in self.metamap:
            if context_match(self.context,pattern):
                self.metahandler = None
                
    def pull_object(self,type):
        #should get merged into make_object
        self.objects.pull(type)
        self.current_object[type] = None
        self.meta_memory[type] = None
        self.objects_max = [max(x,y) for x,y in zip(self.objects.v,self.objects_max)]
        #should pull from the toms stack here.


#And a few helper functions.


def emit_object(destination, type, content, vector, *bonus):
    print >> destination, "%s %s %s %s" % (type,
                                           content,
                                           " ".join(str(x) for x in vector),
                                           " ".join(str(x) for x in bonus)
                                          )

def context_match(context,pattern): # should be modified to simply IGNORE @attributes
    nodes = [x for x in pattern.split("/") if x != ""]
    for node in nodes:
        if node in context:
            position = context.index(node)
            context = context[position:]
        else:
            return False
    return True

def split_attribute_leaf(pattern): # should return any trailing @attribute leaf node from a path.
    return (pattern,None)

if __name__ == "__main__":
    import sys
    did = 1
    files = sys.argv[1:]
    for docid, filename in enumerate(files):
        f = open(filename)
        o = codecs.getwriter('UTF-8')(sys.stdout)
        p = AbstractParser(filename,docid)
        spec,counts = p.parse(f,o)
        print "%s\n%d total tokens in %d unique types." % (spec,sum(counts.values()),len(counts.keys()))
