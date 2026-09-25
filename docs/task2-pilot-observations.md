# Manual review of the label pilot

Read alongside [the six raw-path excerpts](results/task2_pilot_review.md). These checks supplement the automated validation of all 99 labels; they do not compare OpenSTA with another timing engine.

For GCD, the low-arrival example ends at `ctrl.state.out[0]` and selects the falling arrival, 0.716176033 ns. The middle example ends at `dpath.a_reg.out[12]` and selects the rising arrival, 0.958895326 ns. The high example ends at `dpath.b_reg.out[9]` and selects the falling arrival, 1.025362253 ns. Each raw report's final data pin is the requested D pin, its final accumulated time matches the selected label, and the direct-arrival query agrees.

Some GCD canonical IDs are aliases such as `dpath.a_lt_b$in0[12]`, rather than the register instance's preferred display name. The alias inventory connects that comparator-input wire and `dpath.a_reg.out[12]` to the same register Q net. The mapping uses shared bit aliases and rejects ambiguity; it does not infer that a comparator input is a separate register. Preserve both the alias identity and mapped register name in reports.

For TIMER32, the low example (`TMR[1]`, 0.452839226 ns) and high example (`TMR[31]`, 1.244409680 ns) start at the constrained input `PRE[6]`. The RTL compares PRE to the prescaler and uses that result to enable the timer's next-state logic, so this input-to-register path is structurally plausible. The middle example (`clkdiv[22]`, 0.694984615 ns) starts at `clkdiv[0]`. These examples show why the chosen label includes both primary-input and register origins, and why input-delay assumptions matter.

The sums of displayed path increments agree with reported arrivals within the 1e-6 ns validation tolerance; small differences come from displayed finite precision and accumulation. Direct pin-arrival maxima also agree with each transition's path query within 1e-7 ns. This checks query selection and parsing, not commercial-tool fidelity.

TIMER32's target netlist uses `DFFR_X1`, whereas the restricted BOG uses `DFFRS_X1`. The target proof passes and the restricted proof remains unresolved. Investigating the combined set/reset cell model is a motivated next experiment, not a confirmed root cause. All TIMER32 training-eligibility flags remain false.
