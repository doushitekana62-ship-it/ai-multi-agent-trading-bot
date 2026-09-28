# Mirei — SPEC_RUMUS v1

Status: dikunci untuk Phase 1. Perubahan perilaku wajib mengubah spesifikasi dan test.

## 1. Modal awal dan re-entry

- `initialCapitalIdr` adalah nominal modal awal cycle.
- Setiap re-entry memakai `initialCapitalIdr` yang sama.
- Profit/loss cycle sebelumnya tidak menambah nominal re-entry.
- Jika saldo tersedia < `initialCapitalIdr`, keputusan adalah `REENTRY_WAIT`; nominal tidak diperkecil.
- Harga re-entry tidak dibatasi oleh harga entry sebelumnya. Harga lebih rendah, sama, atau lebih tinggi tetap valid.
- Cooldown hanya mencegah duplicate buy dalam interval cooldown.

## 2. Stop Loss

`stopLossPercent = 0` berarti SL OFF.

Jika SL OFF:
- `stopLossPrice = 0`.
- engine tidak menghasilkan `SELL_STOP_LOSS`.
- posisi tidak boleh dijual otomatis hanya karena rugi.

Jika SL > 0:
`stopLossAmountIdr = referenceCapitalIdr * stopLossPercent / 100`.

Untuk reference ENTRY_PRICE:
`referenceCapitalIdr = stakeIdr`.

Untuk reference INITIAL_CAPITAL:
`referenceCapitalIdr = initialCapitalIdr`.

`quantity = stakeIdr / entryPrice`.
`stopLossPrice = entryPrice - stopLossAmountIdr / quantity`.

## 3. Take Profit

TP adalah target NET profit dalam Rupiah setelah biaya eksekusi.

Tanpa execution-cost profile:
`takeProfitPrice = entryPrice + targetNetIdr / quantity`.

Dengan biaya:
- `buyFeeIdr = stakeIdr * buyFeePercent / (100 + buyFeePercent)`.
- `entryNotional = stakeIdr - buyFeeIdr`.
- `executionEntryPrice = entryPrice * (1 + (spread/2 + slippage)/100)`.
- `executedQuantity = entryNotional / executionEntryPrice`.
- `exitMultiplier = (1 - (spread/2 + slippage)/100) * (1 - sellFeePercent/100)`.
- `takeProfitPrice = (stakeIdr + targetNetIdr) / (executedQuantity * exitMultiplier)`.

Definisi target berarti hasil bersih penutupan harus mencapai sekurang-kurangnya modal posisi + `targetNetIdr`, berdasarkan model biaya yang digunakan.

## 4. Batas posisi

`maxOpenPositions` valid hanya pada rentang 1..10. Default saat ini 10.

## 5. Offline

Internet hilang ketika runtime RUNNING -> `HOLD_OFFLINE`.
Internet kembali -> runtime otomatis kembali RUNNING jika session masih aktif.
Offline tidak boleh dianggap sebagai manual HOLD.

## 6. Re-entry pending

Sebelum order re-entry dikirim:
1. cycle state diubah menjadi `REENTRY_PENDING`.
2. state tersebut dipersist.
3. baru execution dipanggil.

Setelah restart, `REENTRY_PENDING` tidak boleh otomatis mengirim order kedua tanpa reconciliation terhadap hasil order sebelumnya.

## 7. CLOSE ALL

Setiap posisi diproses independen.
- Sukses -> cycle menjadi `CLOSED`.
- Gagal -> posisi tetap aktif dan kegagalan symbol/reason dilaporkan.
- `CLOSE ALL` tidak boleh menghapus posisi yang belum benar-benar berhasil ditutup.

## 8. Mode execution

Paper dan Live adalah mode aplikasi berbeda.
- PAPER menggunakan `PaperBroker`.
- LIVE saat ini locked dan tidak boleh mengirim order.
- trade dan audit menyimpan `mode` sebagai NOT NULL.
- database dan session preferences menggunakan namespace mode masing-masing.

## 9. Biaya

Model saat ini menggunakan buy fee, sell fee, spread, slippage, latency, dan minimum order dari `ExecutionCostProfile`.
Komponen biaya lain tidak boleh diasumsikan sebelum sumber resmi exchange diverifikasi.