
### alternating - residency rent vs. reactivations

| policy | reactivations | rent (token-turns) | on frontier |
|---|---|---|---|
| static | 0 | 2,626,400 | dominated |
| search-only | 0 | 125,820 | dominated |
| ttl-20 | 0 | 125,820 | dominated |
| ttl-5 | 0 | 125,820 | dominated |
| lru-8 | 0 | 125,820 | dominated |
| no-cache | 78 | 125,820 | dominated |
| ski-rental | 78 | 63,600 | **yes** |
| min-loads | 0 | 125,610 | **yes** |
| rent-optimal | 78 | 63,600 | **yes** |
| opt@D=0 | 78 | 63,600 | **yes** |
| opt@D=150 | 78 | 63,600 | **yes** |
| opt@D=1,000 | 39 | 71,790 | **yes** |
| opt@D=5,000 | 0 | 125,610 | **yes** |
| opt@D=20,000 | 0 | 125,610 | **yes** |
| opt@D=100,000 | 0 | 125,610 | **yes** |

Dominated outright: static, search-only, ttl-20, ttl-5, lru-8, no-cache. A dominated policy cannot be rescued by any exchange rate between the two axes - something else is cheaper on both.

```text
  2,626,399 |a                                                         
  2,049,434 |                                                          
  1,599,215 |                                                          
  1,247,900 |                                                          
    973,762 |                                                          
    759,847 |                                                          
    592,924 |                                                          
    462,671 |                                                          
    361,031 |                                                          
    281,720 |                                                          
    219,832 |                                                          
    171,539 |                                                          
    133,856 |                                                          
    104,450 |*                                                        f
     81,504 |                                                          
     63,600 |                            .                            *
            +----------------------------------------------------------
             0                 reactivations                  78

  rent, log scale.  a=static  b=search-only  c=ttl-20  d=ttl-5
                   e=lru-8  f=no-cache  g=ski-rental  h=min-loads
                   i=rent-optimal
  . = the optimum at a range of reactivation prices (this is the frontier)
  * = overlapping points
```

### burst - residency rent vs. reactivations

| policy | reactivations | rent (token-turns) | on frontier |
|---|---|---|---|
| static | 0 | 952,070 | dominated |
| search-only | 0 | 25,650 | dominated |
| ttl-20 | 0 | 25,650 | dominated |
| ttl-5 | 0 | 25,650 | dominated |
| lru-8 | 0 | 25,650 | dominated |
| no-cache | 0 | 23,010 | dominated |
| ski-rental | 25 | 20,730 | dominated |
| min-loads | 0 | 20,730 | **yes** |
| rent-optimal | 0 | 20,730 | **yes** |
| opt@D=0 | 0 | 20,730 | **yes** |
| opt@D=150 | 0 | 20,730 | **yes** |
| opt@D=1,000 | 0 | 20,730 | **yes** |
| opt@D=5,000 | 0 | 20,730 | **yes** |
| opt@D=20,000 | 0 | 20,730 | **yes** |
| opt@D=100,000 | 0 | 20,730 | **yes** |

Dominated outright: static, search-only, ttl-20, ttl-5, lru-8, no-cache, ski-rental. A dominated policy cannot be rescued by any exchange rate between the two axes - something else is cheaper on both.

```text
    952,070 |a                                                         
    737,673 |                                                          
    571,557 |                                                          
    442,848 |                                                          
    343,123 |                                                          
    265,855 |                                                          
    205,987 |                                                          
    159,601 |                                                          
    123,660 |                                                          
     95,813 |                                                          
     74,237 |                                                          
     57,519 |                                                          
     44,566 |                                                          
     34,530 |                                                          
     26,754 |                                                          
     20,730 |*                                                        g
            +----------------------------------------------------------
             0                 reactivations                  25

  rent, log scale.  a=static  b=search-only  c=ttl-20  d=ttl-5
                   e=lru-8  f=no-cache  g=ski-rental  h=min-loads
                   i=rent-optimal
  . = the optimum at a range of reactivation prices (this is the frontier)
  * = overlapping points
```

### late_reuse - residency rent vs. reactivations

| policy | reactivations | rent (token-turns) | on frontier |
|---|---|---|---|
| static | 0 | 3,414,320 | dominated |
| search-only | 0 | 104,940 | dominated |
| ttl-20 | 1 | 54,380 | dominated |
| ttl-5 | 1 | 44,780 | dominated |
| lru-8 | 0 | 104,940 | dominated |
| no-cache | 1 | 41,580 | dominated |
| ski-rental | 102 | 40,560 | dominated |
| min-loads | 0 | 104,560 | **yes** |
| rent-optimal | 1 | 40,560 | **yes** |
| opt@D=0 | 1 | 40,560 | **yes** |
| opt@D=150 | 1 | 40,560 | **yes** |
| opt@D=1,000 | 1 | 40,560 | **yes** |
| opt@D=5,000 | 1 | 40,560 | **yes** |
| opt@D=20,000 | 1 | 40,560 | **yes** |
| opt@D=100,000 | 0 | 104,560 | **yes** |

Dominated outright: static, search-only, ttl-20, ttl-5, lru-8, no-cache, ski-rental. A dominated policy cannot be rescued by any exchange rate between the two axes - something else is cheaper on both.

```text
  3,414,320 |a                                                         
  2,540,721 |                                                          
  1,890,645 |                                                          
  1,406,899 |                                                          
  1,046,925 |                                                          
    779,056 |                                                          
    579,724 |                                                          
    431,394 |                                                          
    321,016 |                                                          
    238,880 |                                                          
    177,759 |                                                          
    132,277 |                                                          
     98,432 |*                                                         
     73,247 |                                                          
     54,506 |                                                          
     40,559 |*                                                        g
            +----------------------------------------------------------
             0                 reactivations                  102

  rent, log scale.  a=static  b=search-only  c=ttl-20  d=ttl-5
                   e=lru-8  f=no-cache  g=ski-rental  h=min-loads
                   i=rent-optimal
  . = the optimum at a range of reactivation prices (this is the frontier)
  * = overlapping points
```

### long_mixed - residency rent vs. reactivations

| policy | reactivations | rent (token-turns) | on frontier |
|---|---|---|---|
| static | 0 | 30,794,540 | dominated |
| search-only | 0 | 17,432,290 | dominated |
| ttl-20 | 149 | 5,465,720 | dominated |
| ttl-5 | 245 | 3,096,400 | dominated |
| lru-8 | 145 | 6,455,970 | dominated |
| no-cache | 690 | 1,426,360 | dominated |
| ski-rental | 912 | 805,290 | dominated |
| min-loads | 0 | 15,339,210 | **yes** |
| rent-optimal | 690 | 805,290 | **yes** |
| opt@D=0 | 690 | 805,290 | **yes** |
| opt@D=150 | 690 | 805,290 | **yes** |
| opt@D=1,000 | 558 | 875,390 | **yes** |
| opt@D=5,000 | 241 | 1,613,940 | **yes** |
| opt@D=20,000 | 139 | 2,538,950 | **yes** |
| opt@D=100,000 | 70 | 6,141,210 | **yes** |

Dominated outright: static, search-only, ttl-20, ttl-5, lru-8, no-cache, ski-rental. A dominated policy cannot be rescued by any exchange rate between the two axes - something else is cheaper on both.

```text
 30,794,540 |a                                                         
 24,153,067 |                                                          
 18,943,964 |                                                          
 14,858,310 |*                                                         
 11,653,812 |                                                          
  9,140,429 |                                                          
  7,169,108 |                                                          
  5,622,943 |    .    e                                                
  4,410,240 |         c                                                
  3,459,082 |                                                          
  2,713,060 |               d                                          
  2,127,933 |        .                                                 
  1,669,000 |                                                          
  1,309,046 |               .                           f              
  1,026,724 |                                                          
    805,289 |                                  .        i             g
            +----------------------------------------------------------
             0                 reactivations                  912

  rent, log scale.  a=static  b=search-only  c=ttl-20  d=ttl-5
                   e=lru-8  f=no-cache  g=ski-rental  h=min-loads
                   i=rent-optimal
  . = the optimum at a range of reactivation prices (this is the frontier)
  * = overlapping points
```

### long_tail - residency rent vs. reactivations

| policy | reactivations | rent (token-turns) | on frontier |
|---|---|---|---|
| static | 0 | 7,879,200 | dominated |
| search-only | 0 | 1,091,910 | dominated |
| ttl-20 | 0 | 336,730 | dominated |
| ttl-5 | 14 | 197,530 | dominated |
| lru-8 | 0 | 969,320 | dominated |
| no-cache | 87 | 104,500 | dominated |
| ski-rental | 228 | 67,930 | dominated |
| min-loads | 0 | 162,250 | **yes** |
| rent-optimal | 87 | 67,930 | **yes** |
| opt@D=0 | 87 | 67,930 | **yes** |
| opt@D=150 | 87 | 67,930 | **yes** |
| opt@D=1,000 | 25 | 90,010 | **yes** |
| opt@D=5,000 | 3 | 142,900 | **yes** |
| opt@D=20,000 | 0 | 162,250 | **yes** |
| opt@D=100,000 | 0 | 162,250 | **yes** |

Dominated outright: static, search-only, ttl-20, ttl-5, lru-8, no-cache, ski-rental. A dominated policy cannot be rescued by any exchange rate between the two axes - something else is cheaper on both.

```text
  7,879,200 |a                                                         
  5,739,236 |                                                          
  4,180,479 |                                                          
  3,045,075 |                                                          
  2,218,043 |                                                          
  1,615,630 |                                                          
  1,176,830 |                                                          
    857,207 |*                                                         
    624,392 |                                                          
    454,809 |                                                          
    331,285 |c                                                         
    241,309 |                                                          
    175,770 |   d                                                      
    128,031 |h                                                         
     93,258 |                     f                                    
     67,930 |      .              i                                   g
            +----------------------------------------------------------
             0                 reactivations                  228

  rent, log scale.  a=static  b=search-only  c=ttl-20  d=ttl-5
                   e=lru-8  f=no-cache  g=ski-rental  h=min-loads
                   i=rent-optimal
  . = the optimum at a range of reactivation prices (this is the frontier)
  * = overlapping points
```

### phase_shift - residency rent vs. reactivations

| policy | reactivations | rent (token-turns) | on frontier |
|---|---|---|---|
| static | 0 | 1,575,840 | dominated |
| search-only | 0 | 214,660 | dominated |
| ttl-20 | 0 | 174,360 | dominated |
| ttl-5 | 0 | 96,890 | dominated |
| lru-8 | 0 | 214,660 | dominated |
| no-cache | 0 | 60,640 | dominated |
| ski-rental | 40 | 53,390 | dominated |
| min-loads | 0 | 53,390 | **yes** |
| rent-optimal | 0 | 53,390 | **yes** |
| opt@D=0 | 0 | 53,390 | **yes** |
| opt@D=150 | 0 | 53,390 | **yes** |
| opt@D=1,000 | 0 | 53,390 | **yes** |
| opt@D=5,000 | 0 | 53,390 | **yes** |
| opt@D=20,000 | 0 | 53,390 | **yes** |
| opt@D=100,000 | 0 | 53,390 | **yes** |

Dominated outright: static, search-only, ttl-20, ttl-5, lru-8, no-cache, ski-rental. A dominated policy cannot be rescued by any exchange rate between the two axes - something else is cheaper on both.

```text
  1,575,840 |a                                                         
  1,257,501 |                                                          
  1,003,471 |                                                          
    800,758 |                                                          
    638,996 |                                                          
    509,911 |                                                          
    406,903 |                                                          
    324,704 |                                                          
    259,110 |                                                          
    206,766 |*                                                         
    164,997 |c                                                         
    131,666 |                                                          
    105,067 |                                                          
     83,843 |d                                                         
     66,905 |                                                          
     53,389 |*                                                        g
            +----------------------------------------------------------
             0                 reactivations                  40

  rent, log scale.  a=static  b=search-only  c=ttl-20  d=ttl-5
                   e=lru-8  f=no-cache  g=ski-rental  h=min-loads
                   i=rent-optimal
  . = the optimum at a range of reactivation prices (this is the frontier)
  * = overlapping points
```

### short - residency rent vs. reactivations

| policy | reactivations | rent (token-turns) | on frontier |
|---|---|---|---|
| static | 0 | 98,490 | dominated |
| search-only | 0 | 1,580 | dominated |
| ttl-20 | 0 | 1,580 | dominated |
| ttl-5 | 0 | 1,580 | dominated |
| lru-8 | 0 | 1,580 | dominated |
| no-cache | 0 | 1,370 | dominated |
| ski-rental | 0 | 900 | **yes** |
| min-loads | 0 | 900 | **yes** |
| rent-optimal | 0 | 900 | **yes** |
| opt@D=0 | 0 | 900 | **yes** |
| opt@D=150 | 0 | 900 | **yes** |
| opt@D=1,000 | 0 | 900 | **yes** |
| opt@D=5,000 | 0 | 900 | **yes** |
| opt@D=20,000 | 0 | 900 | **yes** |
| opt@D=100,000 | 0 | 900 | **yes** |

Dominated outright: static, search-only, ttl-20, ttl-5, lru-8, no-cache. A dominated policy cannot be rescued by any exchange rate between the two axes - something else is cheaper on both.

```text
     98,489 |a                                                         
     72,019 |                                                          
     52,662 |                                                          
     38,508 |                                                          
     28,159 |                                                          
     20,590 |                                                          
     15,056 |                                                          
     11,010 |                                                          
      8,050 |                                                          
      5,887 |                                                          
      4,304 |                                                          
      3,147 |                                                          
      2,301 |                                                          
      1,683 |                                                          
      1,230 |*                                                         
        899 |*                                                         
            +----------------------------------------------------------
             0                 reactivations                  1

  rent, log scale.  a=static  b=search-only  c=ttl-20  d=ttl-5
                   e=lru-8  f=no-cache  g=ski-rental  h=min-loads
                   i=rent-optimal
  . = the optimum at a range of reactivation prices (this is the frontier)
  * = overlapping points
```
