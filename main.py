if not selected_indicators:
        st.warning("⚠️ 請至少選擇一項指標進行繪圖與編輯！")
    else:
        dfs_to_merge = []
        with st.spinner("智慧連線 Yahoo / FRED API 擷取並對齊異質頻率數據中..."):
            for ind_name in selected_indicators:
                code_item = st.session_state.custom_indicators.get(ind_name, "")
                code = code_item if isinstance(code_item, str) else code_item.get("code", "")
                calc_mode = st.session_state.indicator_transforms.get(ind_name, "原始水準 (Level/Raw)")
                
                if code:
                    s_df = fetch_smart_data(code)
                    if not s_df.empty:
                        # 確保 Date 為 Index 且排序
                        s_df['Date'] = pd.to_datetime(s_df['Date'])
                        s_df = s_df.sort_values('Date').set_index('Date')
                        series = s_df.iloc[:, 0]
                        
                        # 依照該指標各自選擇的處理方式計算
                        if calc_mode == "年增率 (YoY %)":
                            # 智慧頻率偵測與 YoY 計算
                            if len(series) > 1:
                                dates_idx = pd.Series(series.index)
                                avg_diff_days = (dates_idx.diff().dt.days).median()
                                if avg_diff_days > 60 and avg_diff_days <= 120:
                                    shift_n = 4   # 季資料 (Quarterly) 跨 4 期
                                elif avg_diff_days > 300:
                                    shift_n = 1   # 年資料 (Annual) 跨 1 期
                                else:
                                    shift_n = 12  # 月資料 (Monthly) 跨 12 期
                            else:
                                shift_n = 12
                            
                            processed = series.pct_change(shift_n) * 100
                        elif calc_mode == "月/日增額 (Diff)":
                            processed = series.diff()
                        else:
                            processed = series
                            
                        # 為了讓不同頻率（日、季）完美對齊而不互相汙染，我們將其統一轉為月底 (ME) 取最後有效值
                        res_series = processed.resample('ME').last().dropna()
                        res_df = res_series.to_frame(name=ind_name).reset_index()
                        
                        dfs_to_merge.append(res_df)

        if dfs_to_merge:
            # 從第一個 DataFrame 開始逐步 outer join，確保各自的歷史時間軸完整
            combined_df = dfs_to_merge[0]
            for next_df in dfs_to_merge[1:]:
                combined_df = pd.merge(combined_df, next_df, on='Date', how='outer')
            
            combined_df = combined_df.sort_values('Date').tail(60)
            # 改為不盲目全表 ffill，只針對各自欄位做合理內插或保留 NaN，避免日資料與季資料互相覆蓋
            combined_df = combined_df.dropna(how='all', subset=selected_indicators)
            
            combined_df['日期 (YYYY-MM-DD)'] = combined_df['Date'].dt.strftime('%Y-%m-%d')
            display_cols = ['日期 (YYYY-MM-DD)'] + [c for c in combined_df.columns if c not in ['Date', '日期 (YYYY-MM-DD)']]
            display_df = combined_df[display_cols].copy()

            st.subheader("✏️ 數據線上編輯器 (修改數值、點擊 ＋ Add row 手動補充最新資料)")
            edited_df = st.data_editor(display_df, num_rows="dynamic", key="macro_editor")

            if not edited_df.empty:
                chart_df = edited_df.copy()
                chart_df['日期 (YYYY-MM-DD)'] = pd.to_datetime(chart_df['日期 (YYYY-MM-DD)'], errors='coerce')
                chart_df = chart_df.dropna(subset=['日期 (YYYY-MM-DD)']).sort_values('日期 (YYYY-MM-DD)')
                chart_df.set_index('日期 (YYYY-MM-DD)', inplace=True)

                fig = make_subplots(specs=[[{"secondary_y": True}]])
                colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#17becf']
                
                value_cols = [c for c in chart_df.columns if c != '日期 (YYYY-MM-DD)']
                for idx, col in enumerate(value_cols):
                    is_secondary = (idx > 0 and use_secondary_y)
                    chart_df[col] = pd.to_numeric(chart_df[col], errors='coerce')
                    fig.add_trace(
                        go.Scatter(x=chart_df.index, y=chart_df[col], name=str(col), mode='lines+markers', line=dict(width=2.5, color=colors[idx % len(colors)]), connectgaps=True),
                        secondary_y=is_secondary
                    )

                fig.update_layout(
                    title="全球市場與總經數據互動對比圖（異質頻率完美對齊）",
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    template="plotly_dark",
                    height=chart_height
                )
                fig.update_xaxes(title_text="日期")
                fig.update_yaxes(title_text="主指標 (Left Axis)", secondary_y=False)
                if use_secondary_y and len(value_cols) > 1:
                    fig.update_yaxes(title_text="對比指標 (Right Axis)", secondary_y=True)

                st.subheader("📈 市場趨勢雙 Y 軸動態圖表")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("⚠️ 無法連線讀取數據，請確認指標代碼或網路連線。")
