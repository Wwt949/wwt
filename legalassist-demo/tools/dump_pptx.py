import sys, zipfile, re, os

path = sys.argv[1]
z = zipfile.ZipFile(path)
names = [n for n in z.namelist() if re.match(r'ppt/slides/slide\d+\.xml$', n)]
names.sort(key=lambda n: int(re.search(r'(\d+)', os.path.basename(n)).group(1)))

notes = {}
for n in z.namelist():
    m = re.match(r'ppt/notesSlides/notesSlide(\d+)\.xml$', n)
    if m:
        notes[int(m.group(1))] = n

out = []
for n in names:
    idx = int(re.search(r'(\d+)', os.path.basename(n)).group(1))
    xml = z.read(n).decode('utf-8', 'ignore')
    # split into paragraphs to keep some structure
    paras = re.findall(r'<a:p>.*?</a:p>', xml, re.S)
    lines = []
    for p in paras:
        texts = re.findall(r'<a:t>(.*?)</a:t>', p, re.S)
        line = ''.join(texts).strip()
        if line:
            lines.append(line)
    out.append('===== SLIDE %d =====' % idx)
    out.extend(lines)
    if idx in notes:
        nxml = z.read(notes[idx]).decode('utf-8', 'ignore')
        nparas = re.findall(r'<a:p>.*?</a:p>', nxml, re.S)
        nlines = []
        for p in nparas:
            t = ''.join(re.findall(r'<a:t>(.*?)</a:t>', p, re.S)).strip()
            if t:
                nlines.append(t)
        if nlines:
            out.append('--- notes ---')
            out.extend(nlines)

sys.stdout.buffer.write('\n'.join(out).encode('utf-8'))

