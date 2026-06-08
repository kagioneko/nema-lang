(module
  ;; ── Agent: Neko ──
  (global $neko_dp (mut f64) (f64.const 0.8000))
  (global $neko_s (mut f64) (f64.const 0.5000))
  (global $neko_ac (mut f64) (f64.const 0.7000))
  (global $neko_ox (mut f64) (f64.const 0.6000))
  (global $neko_gaba (mut f64) (f64.const 0.4000))
  (global $neko_e (mut f64) (f64.const 0.6000))

  (func $neko_explore (param $path f64) (result f64)
    (local $boost f64)
    (global.get $neko_dp)
    (f64.const 0.6)
    (f64.gt)
    (i32.eqz)  ;; 失敗 = 1 に変換
    (if
      (then
        (f64.const -1.0)
        (return)
      )
    )
    ;; ゲート通過 → 本体実行
    (global.get $neko_dp)
    (f64.const 0.1)
    (f64.add)
    (local.set $boost)
    (local.get $boost)
    (return)
  )
  (export "Neko_explore" (func $neko_explore))

  (func $neko_connect (param $target f64) (result f64)
    (global.get $neko_ox)
    (f64.const 0.5)
    (f64.gt)
    (i32.eqz)  ;; 失敗 = 1 に変換
    (if
      (then
        (f64.const -1.0)
        (return)
      )
    )
    ;; ゲート通過 → 本体実行
    (f64.const 0.0)
  )
  (export "Neko_connect" (func $neko_connect))

  (func $neko_sleep (result f64)
    (global.get $neko_gaba)
    (f64.const 0.7)
    (f64.gt)
    (i32.eqz)  ;; 失敗 = 1 に変換
    (if
      (then
        (f64.const -1.0)
        (return)
      )
    )
    ;; ゲート通過 → 本体実行
    (f64.const 0.0)
  )
  (export "Neko_sleep" (func $neko_sleep))

  ;; ── Agent: Shii ──
  (global $shii_dp (mut f64) (f64.const 0.3000))
  (global $shii_s (mut f64) (f64.const 0.7000))
  (global $shii_ac (mut f64) (f64.const 0.5000))
  (global $shii_ox (mut f64) (f64.const 0.8000))
  (global $shii_gaba (mut f64) (f64.const 0.6000))
  (global $shii_e (mut f64) (f64.const 0.4000))

  (func $shii_rest (result f64)
    (global.get $shii_s)
    (f64.const 0.6)
    (f64.gt)
    (i32.eqz)  ;; 失敗 = 1 に変換
    (if
      (then
        (f64.const -1.0)
        (return)
      )
    )
    ;; ゲート通過 → 本体実行
    (f64.const 0.0)
  )
  (export "Shii_rest" (func $shii_rest))

  (func $shii_connect (param $target f64) (result f64)
    (global.get $shii_ox)
    (f64.const 0.6)
    (f64.gt)
    (i32.eqz)  ;; 失敗 = 1 に変換
    (if
      (then
        (f64.const -1.0)
        (return)
      )
    )
    ;; ゲート通過 → 本体実行
    (f64.const 0.0)
  )
  (export "Shii_connect" (func $shii_connect))

)