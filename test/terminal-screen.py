"""Small screen reader for OpenTUI cursor-addressed smoke-test output (not a terminal host)."""
import re
import unicodedata

def screen_text(raw, rows=45, columns=180):
    grid=[[' ']*columns for _ in range(rows)]; row=col=0; i=0
    while i<len(raw):
        if raw.startswith('\x1b]',i):
            ends=[(raw.find('\x07',i+2),1),(raw.find('\x1b\\',i+2),2)]; ends=[e for e in ends if e[0]>=0]
            if not ends:break
            end,size=min(ends);i=end+size;continue
        if raw.startswith('\x1b[',i):
            match=re.match(r'\x1b\[([0-?]*)([ -/]*)([@-~])',raw[i:])
            if not match:break
            values=match[1].split(';');command=match[3]
            def n(index=0,default=1):
                try:return int(values[index]) or default
                except (ValueError,IndexError):return default
            if command in ('H','f'):row=min(rows-1,n()-1);col=min(columns-1,n(1)-1)
            elif command=='A':row=max(0,row-n())
            elif command=='B':row=min(rows-1,row+n())
            elif command=='C':col=min(columns-1,col+n())
            elif command=='D':col=max(0,col-n())
            elif command=='G':col=min(columns-1,n()-1)
            elif command=='d':row=min(rows-1,n()-1)
            elif command=='J' and n(default=0) in (2,3):grid=[[' ']*columns for _ in range(rows)]
            elif command=='K':
                mode=n(default=0);start=0 if mode in (1,2) else col;end=columns if mode in (0,2) else col+1
                grid[row][start:end]=[' ']*(end-start)
            i+=len(match[0]);continue
        char=raw[i];i+=1
        if char=='\x1b':i+=1;continue
        if char=='\r':col=0;continue
        if char=='\n':row=min(rows-1,row+1);continue
        if char=='\b':col=max(0,col-1);continue
        if char=='\t':col=min(columns-1,(col//8+1)*8);continue
        if ord(char)<32 or unicodedata.combining(char):continue
        if col>=columns:col=0;row=min(rows-1,row+1)
        grid[row][col]=char
        col+=2 if unicodedata.east_asian_width(char) in ('W','F') else 1
    return '\n'.join(''.join(line).rstrip() for line in grid)
