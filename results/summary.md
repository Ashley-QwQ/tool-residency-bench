# Results

Cost model: discovery=150, search_turn=True. `token-turns` is the sum, over every turn, of the schema tokens resident on that turn. `total tokens` adds the one-off discovery and re-search costs on top.

### `alternating`

Two tools, strictly interleaved, 80 turns. The trap for eviction policies that are too eager: evicting on last use turns every single turn into a cache miss. Aggressive eviction is not free, and this is the trace that proves it.

80 turns &middot; 2 distinct tools used &middot; catalog of 42 tools (32,830 tokens if all resident)

| policy | token-turns | mean | peak | peak # | searches | reloads | thrash | total tokens | vs search-only |
|---|---|---|---|---|---|---|---|---|---|
| static | 2,626,400 | 32,830 | 32,830 | 42 | 0 | 0 | 0% | 2,626,400 | +1979% |
| search-only | 125,820 | 1,573 | 1,590 | 2 | 2 | 0 | 0% | 126,330 | baseline |
| ttl-20 | 125,820 | 1,573 | 1,590 | 2 | 2 | 0 | 0% | 126,330 | +0% |
| ttl-5 | 125,820 | 1,573 | 1,590 | 2 | 2 | 0 | 0% | 126,330 | +0% |
| lru-8 | 125,820 | 1,573 | 1,590 | 2 | 2 | 0 | 0% | 126,330 | +0% |
| no-cache | 125,820 | 1,573 | 1,590 | 2 | 80 | 78 | 98% | 200,040 | +58% |
| oracle-16 | 125,610 | 1,570 | 1,590 | 2 | 2 | 0 | 0% | 126,120 | -0% |
| belady-min | 125,610 | 1,570 | 1,590 | 2 | 2 | 0 | 0% | 126,120 | -0% |

```text
  1,590 | ###################################################################
  1,445 |                                                                    
  1,300 |                                                                    
  1,156 |                                                                    
  1,011 |                                                                    
    867 |                                                                    
    722 |                                                                    
    578 |                                                                    
    433 |                                                                    
    289 |                                                                    
    144 |#                                                                   
      0 |                                                                    
        +--------------------------------------------------------------------
         0                            turn                            80
         # search-only  * ttl-20  o ttl-5  + oracle-16
         (curves that coincide are drawn once, in legend order)
```

### `burst`

Grayscale 26 images, then post one, then search, then notify. The grayscale tool is by a wide margin the most recently and most frequently used tool in the trace at the moment it becomes dead weight. Recency and frequency both point exactly the wrong way here, which is why LRU and LFU cannot be the whole answer.

29 turns &middot; 4 distinct tools used &middot; catalog of 42 tools (32,830 tokens if all resident)

| policy | token-turns | mean | peak | peak # | searches | reloads | thrash | total tokens | vs search-only |
|---|---|---|---|---|---|---|---|---|---|
| static | 952,070 | 32,830 | 32,830 | 42 | 0 | 0 | 0% | 952,070 | +2954% |
| search-only | 25,650 | 884 | 3,230 | 4 | 4 | 0 | 0% | 31,170 | baseline |
| ttl-20 | 25,650 | 884 | 3,230 | 4 | 4 | 0 | 0% | 31,170 | +0% |
| ttl-5 | 25,650 | 884 | 3,230 | 4 | 4 | 0 | 0% | 31,170 | +0% |
| lru-8 | 25,650 | 884 | 3,230 | 4 | 4 | 0 | 0% | 31,170 | +0% |
| no-cache | 23,010 | 793 | 1,940 | 2 | 4 | 0 | 0% | 25,890 | -17% |
| oracle-16 | 20,730 | 715 | 1,240 | 1 | 4 | 0 | 0% | 21,330 | -32% |
| belady-min | 20,730 | 715 | 1,240 | 1 | 4 | 0 | 0% | 21,330 | -32% |

```text
  3,230 |                                                                  ##
  2,936 |                                                                    
  2,642 |                                                                    
  2,349 |                                                                    
  2,055 |                                                                ##  
  1,761 |                                                             ###    
  1,468 |                                                                    
  1,174 |                                                             +++    
    880 |                                                                  ++
    587 |#############################################################       
    293 |                                                                ++  
      0 |                                                                    
        +--------------------------------------------------------------------
         0                            turn                            29
         # search-only  * ttl-20  o ttl-5  + oracle-16
         (curves that coincide are drawn once, in legend order)
```

### `late_reuse`

A tool is used three times, sits idle for 100 turns, then is needed once more. 'It will be needed again' is true here and is still not a reason to keep it: the question is whether 100 turns of rent is cheaper than one re-search. This trace is where the discovery-cost knob actually decides the answer - sweep it.

104 turns &middot; 2 distinct tools used &middot; catalog of 42 tools (32,830 tokens if all resident)

| policy | token-turns | mean | peak | peak # | searches | reloads | thrash | total tokens | vs search-only |
|---|---|---|---|---|---|---|---|---|---|
| static | 3,414,320 | 32,830 | 32,830 | 42 | 0 | 0 | 0% | 3,414,320 | +3125% |
| search-only | 104,940 | 1,009 | 1,020 | 2 | 2 | 0 | 0% | 105,880 | baseline |
| ttl-20 | 54,380 | 523 | 1,020 | 2 | 3 | 1 | 0% | 55,850 | -47% |
| ttl-5 | 44,780 | 431 | 1,020 | 2 | 3 | 1 | 0% | 46,250 | -56% |
| lru-8 | 104,940 | 1,009 | 1,020 | 2 | 2 | 0 | 0% | 105,880 | +0% |
| no-cache | 41,580 | 400 | 1,020 | 2 | 3 | 1 | 0% | 43,050 | -59% |
| oracle-16 | 40,560 | 390 | 640 | 1 | 3 | 1 | 0% | 41,010 | -61% |
| belady-min | 104,560 | 1,005 | 1,020 | 2 | 2 | 0 | 0% | 105,500 | -0% |

```text
  1,020 |  ##################################################################
    927 |                                                                    
    834 |                                                                    
    741 |                                                                    
    649 |                                                                    
    556 |##                                                                 +
    463 |                                                                    
    370 |  ++++oooooooooo*************************************************** 
    278 |                                                                    
    185 |                                                                    
     92 |                                                                    
      0 |                                                                    
        +--------------------------------------------------------------------
         0                            turn                            104
         # search-only  * ttl-20  o ttl-5  + oracle-16
         (curves that coincide are drawn once, in legend order)
```

### `long_mixed`

Roughly a thousand turns of realistic mixture: five recurring phases over eight cycles, with occasional random detours across the whole catalog. Phases repeat, so tools genuinely do come back - which is what makes this harder than a clean phase shift and is the closest thing here to a real long-horizon session.

938 turns &middot; 26 distinct tools used &middot; catalog of 42 tools (32,830 tokens if all resident)

| policy | token-turns | mean | peak | peak # | searches | reloads | thrash | total tokens | vs search-only |
|---|---|---|---|---|---|---|---|---|---|
| static | 30,794,540 | 32,830 | 32,830 | 42 | 0 | 0 | 0% | 30,794,540 | +74% |
| search-only | 17,432,290 | 18,585 | 20,930 | 26 | 26 | 0 | 0% | 17,692,490 | baseline |
| ttl-20 | 5,465,720 | 5,827 | 9,960 | 9 | 175 | 149 | 1% | 6,347,860 | -64% |
| ttl-5 | 3,096,400 | 3,301 | 7,790 | 7 | 271 | 245 | 29% | 3,914,760 | -78% |
| lru-8 | 6,455,970 | 6,883 | 11,080 | 9 | 171 | 145 | 0% | 7,606,050 | -57% |
| no-cache | 1,426,360 | 1,521 | 2,930 | 2 | 716 | 690 | 62% | 2,154,830 | -88% |
| oracle-16 | 2,405,900 | 2,565 | 4,430 | 4 | 175 | 149 | 0% | 2,632,510 | -85% |
| belady-min | 15,339,210 | 16,353 | 19,280 | 22 | 26 | 0 | 0% | 15,592,740 | -12% |

```text
 20,930 |                                                           #########
 19,027 |             ##############################################         
 17,124 |       ######                                                       
 15,221 |                                                                    
 13,319 |      #                                                             
 11,416 |     #                                                              
  9,513 |                                                                 *  
  7,610 |   ## ***  ******    ****    *****   *****    ***     ****     ** * 
  5,708 |   * * o   o   o    *   o*  *oo o *    o  *   oo **   o o ***      *
  3,805 |  #oooo+o**+ooo+o***oooo+o**o++o+o **+o ooo***++ooo***+o+o+o  *o+ooo
  1,902 | #++ +  +oo      +oo+  +   o+    +ooo  ++   +o   + ooo   +   *o     
      0 |#        +                o       +        +       +        o       
        +--------------------------------------------------------------------
         0                            turn                            938
         # search-only  * ttl-20  o ttl-5  + oracle-16
         (curves that coincide are drawn once, in legend order)
```

### `long_tail`

Two workhorse tools carry the task, interrupted every so often by a one-off specialist that is never needed again. This is the everyday shape of a long session, and it is what makes monotonic loading fail slowly enough that nobody notices until the context is full.

240 turns &middot; 12 distinct tools used &middot; catalog of 42 tools (32,830 tokens if all resident)

| policy | token-turns | mean | peak | peak # | searches | reloads | thrash | total tokens | vs search-only |
|---|---|---|---|---|---|---|---|---|---|
| static | 7,879,200 | 32,830 | 32,830 | 42 | 0 | 0 | 0% | 7,879,200 | +594% |
| search-only | 1,091,910 | 4,550 | 9,710 | 12 | 12 | 0 | 0% | 1,135,110 | baseline |
| ttl-20 | 336,730 | 1,403 | 2,260 | 3 | 12 | 0 | 0% | 345,360 | -70% |
| ttl-5 | 197,530 | 823 | 2,260 | 3 | 26 | 14 | 38% | 216,440 | -81% |
| lru-8 | 969,320 | 4,039 | 7,730 | 9 | 12 | 0 | 0% | 1,008,700 | -11% |
| no-cache | 104,500 | 435 | 1,830 | 2 | 99 | 87 | 74% | 155,920 | -86% |
| oracle-16 | 154,080 | 642 | 2,260 | 3 | 13 | 1 | 0% | 162,640 | -86% |
| belady-min | 162,250 | 676 | 2,260 | 3 | 12 | 0 | 0% | 170,880 | -85% |

```text
  9,710 |                                                                ####
  8,827 |                                                                    
  7,944 |                                                          ######    
  7,061 |                                                   #######          
  6,179 |                                            #######                 
  5,296 |                                                                    
  4,413 |                              ##############                        
  3,530 |                                                                    
  2,648 |                        ######                                      
  1,765 |          ##############      *******       *******             ****
    882 |   #######********************o      *******       *************    
      0 |###o++oooo ++oooo +ooooo +oooo ++oooo ++oooo ++oooo +ooooo +oooo ++o
        +--------------------------------------------------------------------
         0                            turn                            240
         # search-only  * ttl-20  o ttl-5  + oracle-16
         (curves that coincide are drawn once, in legend order)
```

### `phase_shift`

download -> process -> upload -> report, twelve turns each. The natural shape of most long agent tasks. A good working set walks [A] -> [B] -> [C] -> [D]; monotonic loading walks [A] -> [A B] -> [A B C] -> [A B C D] and pays for every phase it has already finished.

48 turns &middot; 8 distinct tools used &middot; catalog of 42 tools (32,830 tokens if all resident)

| policy | token-turns | mean | peak | peak # | searches | reloads | thrash | total tokens | vs search-only |
|---|---|---|---|---|---|---|---|---|---|
| static | 1,575,840 | 32,830 | 32,830 | 42 | 0 | 0 | 0% | 1,575,840 | +547% |
| search-only | 214,660 | 4,472 | 8,580 | 8 | 8 | 0 | 0% | 243,480 | baseline |
| ttl-20 | 174,360 | 3,632 | 5,870 | 5 | 8 | 0 | 0% | 197,850 | -19% |
| ttl-5 | 96,890 | 2,019 | 3,910 | 3 | 8 | 0 | 0% | 108,340 | -56% |
| lru-8 | 214,660 | 4,472 | 8,580 | 8 | 8 | 0 | 0% | 243,480 | +0% |
| no-cache | 60,640 | 1,263 | 2,570 | 2 | 8 | 0 | 0% | 69,090 | -72% |
| oracle-16 | 53,390 | 1,112 | 1,550 | 1 | 8 | 0 | 0% | 54,590 | -78% |
| belady-min | 53,390 | 1,112 | 1,550 | 1 | 8 | 0 | 0% | 54,590 | -78% |

```text
  8,580 |                                                            ########
  7,800 |                                                                    
  7,020 |                                                   #########        
  6,240 |                                                                    
  5,460 |                                            #######******** ****    
  4,680 |                                  ##########***                 ****
  3,900 |                                  ooo  *****   ****        *        
  3,120 |                             #####                 oo               
  2,340 |                 ############ooooo   oooooo                 oooooooo
  1,560 |                 ooooooooo                  ooooooo  ooooooo        
    780 |#################+++++++++ooo++++++++++++++o       +++++++++++++++++
      0 |         ++++++++                           +++++++                 
        +--------------------------------------------------------------------
         0                            turn                            48
         # search-only  * ttl-20  o ttl-5  + oracle-16
         (curves that coincide are drawn once, in legend order)
```

### `short`

A two-tool errand. Nothing accumulates and nothing needs managing. This trace exists to check the opposite claim from the rest of the suite: residency management must not make small tasks worse. Any policy that loses here is disqualified regardless of how well it does on the long traces.

3 turns &middot; 3 distinct tools used &middot; catalog of 42 tools (32,830 tokens if all resident)

| policy | token-turns | mean | peak | peak # | searches | reloads | thrash | total tokens | vs search-only |
|---|---|---|---|---|---|---|---|---|---|
| static | 98,490 | 32,830 | 32,830 | 42 | 0 | 0 | 0% | 98,490 | +3534% |
| search-only | 1,580 | 527 | 900 | 3 | 3 | 0 | 0% | 2,710 | baseline |
| ttl-20 | 1,580 | 527 | 900 | 3 | 3 | 0 | 0% | 2,710 | +0% |
| ttl-5 | 1,580 | 527 | 900 | 3 | 3 | 0 | 0% | 2,710 | +0% |
| lru-8 | 1,580 | 527 | 900 | 3 | 3 | 0 | 0% | 2,710 | +0% |
| no-cache | 1,370 | 457 | 690 | 2 | 3 | 0 | 0% | 2,290 | -15% |
| oracle-16 | 900 | 300 | 430 | 1 | 3 | 0 | 0% | 1,350 | -50% |
| belady-min | 900 | 300 | 430 | 1 | 3 | 0 | 0% | 1,350 | -50% |

```text
    900 |                                              ######################
    818 |                                                                    
    736 |                                                                    
    654 |                                                                    
    572 |                                                                    
    490 |                                                                    
    409 |                       #######################++++++++++++++++++++++
    327 |                                                                    
    245 |                       +++++++++++++++++++++++                      
    163 |#######################                                             
     81 |                                                                    
      0 |                                                                    
        +--------------------------------------------------------------------
         0                            turn                            3
         # search-only  * ttl-20  o ttl-5  + oracle-16
         (curves that coincide are drawn once, in legend order)
```
