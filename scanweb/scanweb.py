import web
import collections
import subprocess as S
import os, os.path, datetime, sys, re
import datetime, threading

urls = (
    '/',                     'index',
    '/(view|download)/(.*)', 'get_pdf',
    '/print/(.*)',           'print_',
)

render = web.template.render('templates/')

class Scan(collections.namedtuple("Scan", "name date pages")):
    pass

class PDFInfoManager(object):
    """Fetch and cache info about PDFs"""

    # A dictionary mapping filenames to cache entries (of type E, defined
    # below)
    cache = None

    #  An entry in the cache.  Currently E.expire is used to decide when to
    #  expunge an entry from the cache, but if an expired entry is still
    #  present in the cache, it will be returned.
    E = collections.namedtuple("E", "st expire info")

    # To synchronize access from multiple threads
    lock = None

    def __init__(self):
        self.cache = {}
        self.lock = threading.Lock()

    def get_info(self, fn):
        st = os.stat(fn)
        expire = datetime.datetime.now() + datetime.timedelta(days=7)

        with self.lock:
            # If there's a match in the cache, return it.
            if fn in self.cache:
                e = self.cache[fn]
                if st == e.st:
                    self.cache[fn] = e._replace(expire=expire)
                    return e.info

            # Have to gather the info.
            info = self.get_info_raw(fn)
            self.cache[fn] = self.E(st, expire, info)
            return info

    @staticmethod
    def get_info_raw(fn):
        p = S.Popen(["pdfinfo", os.path.join(SCAN_DIR, fn)], stdin=S.PIPE, stdout=S.PIPE, stderr=S.PIPE)
        out, err = p.communicate()
        if err != "" or p.returncode != 0:
            return None
        pages = date = None
        for line in out.splitlines():
            if line.startswith("Pages:"):
                pages = int(line.split()[1])
            if line.startswith("ModDate:"):
                date = line[8:].strip()
                try:
                    date = datetime.datetime.strptime(date, "%c")
                except RuntimeError:
                    pass
        return Scan(os.path.basename(fn), date, pages)

    def expunge(self):
        now = datetime.datetime.now()
        expired = []
        with self.lock:
            for fn, e in self.cache.iteritems():
                if e.expire > now:
                    expired.append(fn)
            for fn in expired:
                del self.cache[fn]

SCAN_DIR = "/home/mike/scans"
PDF_CACHE = PDFInfoManager()
def get_scans():
    for pdf in os.listdir(SCAN_DIR):
        if pdf.startswith(".") or not pdf.endswith(".pdf"):
            continue
        info = PDF_CACHE.get_info(os.path.join(SCAN_DIR, pdf))
        if info is not None:
            yield info


class index(object):
    def GET(self):
        scans = list(get_scans())
        scans.sort(key=lambda s: s.date, reverse=True)
        return render.index(scans)

    def POST(self):
        # Parse the form arguments and make sure they're sane.
        data = web.input()
        dpi = int(data.get('dpi', 150))
        assert dpi in (150,300,600)
        color = data.get('color', 'lineart')
        assert color in ('lineart', 'gray', 'color')
        duplex = data.get('duplex', None) == 'full'
        name = data.get('name', "scan")
        if not name.endswith('.pdf'):
            name += '.pdf'
        assert '/' not in name
        assert not name.startswith('.')
        assert len(name) > 4

        # Make sure name is unique
        while os.path.exists(os.path.join(SCAN_DIR, name)):
            m = re.match(r'^(.*?)(\d*)(\.pdf)', name)
            assert m
            if m.group(2) == '':
                name = m.group(1) + '_2.pdf' 
            else:
                name = '{}{}{}'.format(m.group(1), int(m.group(2)) + 1, m.group(3))

        # Do the scan
        args = ["../scanpdf", str(dpi), color, 
                    'duplex' if duplex else 'front', os.path.join(SCAN_DIR, name)]
        p = S.Popen(args, stdin=S.PIPE, stdout=S.PIPE, stderr=S.STDOUT)
        out, err = p.communicate()
        if p.returncode != 0:
            print repr(args)
            sys.stdout.write(out)

        # Give the same output as GET would have
        return self.GET()

class get_pdf(object):
    def GET(self, view_or_download, name):
        assert '/' not in name
        assert name.endswith(".pdf")
        web.header('Content-Type', 'application/pdf')
        if view_or_download == "download":
            web.header('Content-Disposition', 'attachment; filename="{}"'.format(name))
        with open(os.path.join(SCAN_DIR, name), "rb") as fh:
            return fh.read()

class print_(object):
    def POST(self, name):
        assert '/' not in name
        p = S.Popen(["lpr", os.path.join(SCAN_DIR, name)], stdin=S.PIPE, stdout=S.PIPE, stderr=S.PIPE)
        p.communicate()
        raise web.seeother("/")


def main():
    app = web.application(urls, globals())
    app.run()

if __name__ == "__main__":
    main()
