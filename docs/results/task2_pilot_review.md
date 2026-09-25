# Task 2 pilot: inspect six matched register bits

These are low-, middle-, and high-arrival examples from each design. All pilot labels were also checked against direct pin arrivals and the sum of the reported path increments. Times are ns. Matching uses RTL aliases, not timing values.

| Design | Register bit | Source kind | Rise | Fall | Selected |
| --- | --- | --- | ---: | ---: | ---: |
| gcd | `ctrl.curr_state__0[0]` | register | 0.696730375 | 0.716176033 | 0.716176033 |
| gcd | `dpath.a_lt_b$in0[12]` | register | 0.958895326 | 0.784162819 | 0.958895326 |
| gcd | `dpath.a_lt_b$in1[9]` | register | 1.008201957 | 1.025362253 | 1.025362253 |
| timer32 | `TMR[1]` | primary_input | 0.447054386 | 0.452839226 | 0.452839226 |
| timer32 | `clkdiv[22]` | register | 0.693285048 | 0.694984615 | 0.694984615 |
| timer32 | `TMR[31]` | primary_input | 1.244409680 | 1.206417203 | 1.244409680 |

## gcd: ctrl.curr_state__0[0]

Mapped D pin: `ctrl.state.out[0]$_SDFF_PP0_/D`. Winning transition: fall. Sum of path increments: 0.716176030 ns. Full report: `data/labels/gcd/path_0_fall.rpt`.

```text
Startpoint: dpath.a_reg.out[0]$_DFFE_PP_
            (rising edge-triggered flip-flop clocked by core_clock)
Endpoint: ctrl.state.out[0]$_SDFF_PP0_
          (rising edge-triggered flip-flop clocked by core_clock)
Path Group: core_clock
Path Type: max
...
     2    3.315186977    0.057802353    0.081521735    0.703182757 ^ $abc$1409$auto$blifparse.cc:397:parse_blif$1516/ZN (NOR4_X1)
                                                                     $abc$1409$new_n246 (net)
                         0.057802353    0.000000000    0.703182757 ^ $abc$1409$auto$blifparse.cc:397:parse_blif$1518/A2 (NOR3_X1)
     1    1.062342048    0.013840448    0.012993273    0.716176033 v $abc$1409$auto$blifparse.cc:397:parse_blif$1518/ZN (NOR3_X1)
                                                                     $abc$1409$auto$rtlil.cc:3513:MuxGate$1290 (net)
                         0.013840448    0.000000000    0.716176033 v ctrl.state.out[0]$_SDFF_PP0_/D (DFF_X1)
                                                       0.716176033    data arrival time
```

## gcd: dpath.a_lt_b$in0[12]

Mapped D pin: `dpath.a_reg.out[12]$_DFFE_PP_/D`. Winning transition: rise. Sum of path increments: 0.958895333 ns. Full report: `data/labels/gcd/path_5_rise.rpt`.

```text
Startpoint: dpath.a_reg.out[0]$_DFFE_PP_
            (rising edge-triggered flip-flop clocked by core_clock)
Endpoint: dpath.a_reg.out[12]$_DFFE_PP_
          (rising edge-triggered flip-flop clocked by core_clock)
Path Group: core_clock
Path Type: max
...
     1    1.520308971    0.055595718    0.041229133    0.898102582 v $abc$1409$auto$blifparse.cc:397:parse_blif$1535/ZN (AOI221_X1)
                                                                     $abc$1409$new_n265 (net)
                         0.055595718    0.000000000    0.898102582 v $abc$1409$auto$blifparse.cc:397:parse_blif$1536/B2 (AOI22_X1)
     1    1.140290022    0.031321850    0.060792763    0.958895326 ^ $abc$1409$auto$blifparse.cc:397:parse_blif$1536/ZN (AOI22_X1)
                                                                     $abc$1409$auto$rtlil.cc:3513:MuxGate$1300 (net)
                         0.031321850    0.000000000    0.958895326 ^ dpath.a_reg.out[12]$_DFFE_PP_/D (DFF_X1)
                                                       0.958895326    data arrival time
```

## gcd: dpath.a_lt_b$in1[9]

Mapped D pin: `dpath.b_reg.out[9]$_DFFE_PP_/D`. Winning transition: fall. Sum of path increments: 1.025362274 ns. Full report: `data/labels/gcd/path_33_fall.rpt`.

```text
Startpoint: dpath.a_reg.out[0]$_DFFE_PP_
            (rising edge-triggered flip-flop clocked by core_clock)
Endpoint: dpath.b_reg.out[9]$_DFFE_PP_
          (rising edge-triggered flip-flop clocked by core_clock)
Path Group: core_clock
Path Type: max
...
    16   30.719076157    0.073362328    0.109845802    0.963268280 ^ $abc$1409$auto$blifparse.cc:397:parse_blif$1573/ZN (OR2_X1)
                                                                     $abc$1409$new_n303 (net)
                         0.073362328    0.000000000    0.963268280 ^ $abc$1409$auto$blifparse.cc:397:parse_blif$1605/S (MUX2_X1)
     1    1.062342048    0.009322899    0.062093999    1.025362253 v $abc$1409$auto$blifparse.cc:397:parse_blif$1605/Z (MUX2_X1)
                                                                     $abc$1409$auto$rtlil.cc:3513:MuxGate$1356 (net)
                         0.009322899    0.000000000    1.025362253 v dpath.b_reg.out[9]$_DFFE_PP_/D (DFF_X1)
                                                       1.025362253    data arrival time
```

## timer32: TMR[1]

Mapped D pin: `TMR[1]$_DFFE_PP0P_/D`. Winning transition: fall. Sum of path increments: 0.452839224 ns. Full report: `data/labels/timer32/path_12_fall.rpt`.

```text
Startpoint: PRE[6] (input port clocked by core_clock)
Endpoint: TMR[1]$_DFFE_PP0P_
          (rising edge-triggered flip-flop clocked by core_clock)
Path Group: core_clock
Path Type: max

...
     4    6.736823082    0.019687051    0.056896016    0.443162382 ^ $abc$1775$auto$blifparse.cc:397:parse_blif$1932/ZN (AND2_X1)
                                                                     $abc$1775$new_n421 (net)
                         0.019687051    0.000000000    0.443162382 ^ $abc$1775$auto$blifparse.cc:397:parse_blif$2047/A1 (NOR3_X1)
     1    1.052731037    0.018216737    0.009676843    0.452839226 v $abc$1775$auto$blifparse.cc:397:parse_blif$2047/ZN (NOR3_X1)
                                                                     $abc$1775$auto$rtlil.cc:3513:MuxGate$1497 (net)
                         0.018216737    0.000000000    0.452839226 v TMR[1]$_DFFE_PP0P_/D (DFFR_X1)
                                                       0.452839226    data arrival time
```

## timer32: clkdiv[22]

Mapped D pin: `clkdiv[22]$_DFFE_PP0P_/D`. Winning transition: fall. Sum of path increments: 0.694984598 ns. Full report: `data/labels/timer32/path_47_fall.rpt`.

```text
Startpoint: clkdiv[0]$_DFFE_PP0P_
            (rising edge-triggered flip-flop clocked by core_clock)
Endpoint: clkdiv[22]$_DFFE_PP0P_
          (rising edge-triggered flip-flop clocked by core_clock)
Path Group: core_clock
Path Type: max
...
     2    3.376521111    0.012016113    0.037531812    0.687155306 ^ $abc$1775$auto$blifparse.cc:397:parse_blif$1872/ZN (AND2_X1)
                                                                     $abc$1775$new_n361 (net)
                         0.012016113    0.000000000    0.687155306 ^ $abc$1775$auto$blifparse.cc:397:parse_blif$1902/A1 (NOR2_X1)
     1    1.052731037    0.007849759    0.007829293    0.694984615 v $abc$1775$auto$blifparse.cc:397:parse_blif$1902/ZN (NOR2_X1)
                                                                     $abc$1775$auto$rtlil.cc:3513:MuxGate$1637 (net)
                         0.007849759    0.000000000    0.694984615 v clkdiv[22]$_DFFE_PP0P_/D (DFFR_X1)
                                                       0.694984615    data arrival time
```

## timer32: TMR[31]

Mapped D pin: `TMR[31]$_DFFE_PP0P_/D`. Winning transition: rise. Sum of path increments: 1.244409719 ns. Full report: `data/labels/timer32/path_25_rise.rpt`.

```text
Startpoint: PRE[6] (input port clocked by core_clock)
Endpoint: TMR[31]$_DFFE_PP0P_
          (rising edge-triggered flip-flop clocked by core_clock)
Path Group: core_clock
Path Type: max

...
     1    1.563845038    0.011102249    0.060658257    1.218418717 v $abc$1775$auto$blifparse.cc:397:parse_blif$2019/Z (XOR2_X1)
                                                                     $abc$1775$new_n508 (net)
                         0.011102249    0.000000000    1.218418717 v $abc$1775$auto$blifparse.cc:397:parse_blif$2020/A2 (NOR2_X1)
     1    1.128276944    0.013238966    0.025990987    1.244409680 ^ $abc$1775$auto$blifparse.cc:397:parse_blif$2020/ZN (NOR2_X1)
                                                                     $abc$1775$auto$rtlil.cc:3513:MuxGate$1549 (net)
                         0.013238966    0.000000000    1.244409680 ^ TMR[31]$_DFFE_PP0P_/D (DFFR_X1)
                                                       1.244409680    data arrival time
```
