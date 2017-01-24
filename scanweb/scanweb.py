import web
import collections
import subprocess as S
import os, datetime, sys, re

urls = (
    '/',                     'index',
    '/(view|download)/(.*)', 'get_pdf',
)

render = web.template.render('templates/')

class Scan(collections.namedtuple("Scan", "name date pages")):
    pass

SCAN_DIR = "/home/mike/scans"
def get_scans():
    for pdf in os.listdir(SCAN_DIR):
        if pdf.startswith(".") or not pdf.endswith(".pdf"):
            continue
        p = S.Popen(["pdfinfo", os.path.join(SCAN_DIR, pdf)], stdin=S.PIPE, stdout=S.PIPE, stderr=S.PIPE)
        out, err = p.communicate()
        if err != "" or p.returncode != 0:
            continue
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
        yield Scan(pdf, date, pages)


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

def main():
    app = web.application(urls, globals())
    app.run()

if __name__ == "__main__":
    main()
