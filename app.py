if mode == "Quét tín hiệu toàn thị trường":
    st.header(f"🔍 Trình quét Top 100 thanh khoản (Khung: {timeframe})")
    
    if st.button("Bắt đầu quét danh mục"):
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty() # Hiển thị mã đang quét
        
        for idx, s in enumerate(TOP_MARKET):
            status_text.text(f" đang kiểm tra: {s} ({idx+1}/{len(TOP_MARKET)})")
            try:
                data = get_data(s, timeframe)
                if data is not None and not data.empty:
                    res = calculate_signals(data)
                    if res:
                        b_score, s_score, _ = res
                        if b_score >= 0.65: status = "🟢 MUA"
                        elif s_score >= 0.5: status = "🔴 BÁN"
                        else: status = "⚪ THEO DÕI"
                        
                        results.append({
                            "Mã": s, 
                            "Trạng thái": status, 
                            "Điểm Mua (%)": int(b_score * 100),
                            "Điểm Bán (%)": int(s_score * 100)
                        })
                # Nghỉ 0.15s mỗi mã để duy trì kết nối ổn định
                time.sleep(0.15) 
            except:
                continue
                
            progress_bar.progress((idx + 1) / len(TOP_MARKET))
        
        status_text.success("✅ Đã hoàn thành quét 100 mã!")
        
        if results:
            res_df = pd.DataFrame(results)
            res_df = res_df.sort_values(by="Điểm Mua (%)", ascending=False).reset_index(drop=True)
            
            # Hiển thị bảng với màu sắc sinh động
            st.dataframe(
                res_df,
                column_config={
                    "Điểm Mua (%)": st.column_config.ProgressColumn("Đồng thuận MUA", format="%d%%", min_value=0, max_value=100),
                    "Điểm Bán (%)": st.column_config.ProgressColumn("Đồng thuận BÁN", format="%d%%", min_value=0, max_value=100),
                },
                use_container_width=True,
                height=600
            )
