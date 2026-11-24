
    
  
                            ))
                            fig_instruments.update_layout(
                                title="Performance par instrument",
                                height=340,
                                template="plotly_dark",
                                paper_bgcolor="rgba(0,0,0,0)",
                                plot_bgcolor="rgba(0,0,0,0)",
                                margin=dict(l=15, r=15, t=55, b=35),
                                yaxis_title="Résultat net (R)",
                                xaxis_title="",
                                showlegend=False,
                                yaxis=dict(zeroline=True, zerolinecolor="#7890aa"),
                            )
                            st.plotly_chart(fig_instruments, width="stretch")
                        else:
                            st.info("Pas encore assez de résultats par instrument.")
                    else:
                        st.info("Les résultats par instrument apparaîtront après les premiers trades clôturés.")

                # 3) Résultat hebdomadaire en R
                if not closed_df.empty and "close_time" in closed_df.columns:
                    weekly_df = closed_df.copy()
                    weekly_df["_close_date"] = pd.to_datetime(
                        weekly_df["close_time"], errors="coerce", utc=True
                    )
                    weekly_df["result_r"] = pd.to_numeric(
                        weekly_df["result_r"], errors="coerce"
                    )
                    weekly_df = weekly_df.dropna(subset=["_close_date", "result_r"])
                    if not weekly_df.empty:
                        weekly_df["_week"] = (
                            weekly_df["_close_date"]
                            .dt.tz_convert("America/New_York")
                            .dt.to_period("W")
                            .astype(str)
                        )
                        weekly_results = (
                            weekly_df.groupby("_week")["result_r"]
                            .sum()
                            .reset_index()
                        )
                        fig_weekly = go.Figure(go.Bar(
                            x=weekly_results["_week"],
                            y=weekly_results["result_r"],
                            marker=dict(
                                color=[
                                    "#20d68a" if value >= 0 else "#ff5b6e"
                                    for value in weekly_results["result_r"]
                                ]
                            ),
                            text=[f"{value:+.2f} R" for value in weekly_results["result_r"]],
                            textposition="outside",
                            hovertemplate="Semaine %{x}<br>Résultat : %{y:+.2f} R<extra></extra>",
                        ))
                        fig_weekly.update_layout(
                            title="Résultat par semaine",
                            height=320,
                            template="plotly_dark",
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            margin=dict(l=20, r=20, t=55, b=45),
                            xaxis_title="Semaine de clôture (heure de New York)",
                            yaxis_title="Résultat net (R)",
                            showlegend=False,
                            yaxis=dict(zeroline=True, zerolinecolor="#7890aa"),
                        )
                        st.plotly_chart(fig_weekly, width="stretch")

            display_columns = [
                "created_at", "instrument", "timeframe", "direction", "fib_mode",
                "entry_price", "stop_loss", "take_profit", "rr", "status",
                "close_price", "close_time", "result_r", "pnl_usd", "notes"
            ]
            available_columns = [c for c in display_columns if c in virtual_df.columns]
            st.dataframe(
                virtual_df[available_columns],
                width="stretch",
                hide_index=True,
                column_config={
                    "pnl_usd": st.column_config.NumberColumn(
                        "P&L simulé ($)", format="%.2f $"
                    ),
                    "result_r": st.column_config.NumberColumn(
                        "Résultat (R)", format="%.2f R"
                    ),
                }
            )
            st.download_button(
                "⬇️ Télécharger l'historique des trades virtuels (CSV)",
                data=virtual_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"trades_virtuels_{datetime.now(pytz.timezone('America/New_York')).strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True,
            )
    except Exception as exc:
        st.error(f"Impossible de charger les trades virtuels depuis Supabase : {exc}")


# RECENT ALERTS AND DOWNLOADABLE HISTORY
st.markdown("---")
st.subheader("🔔 Alertes Fibonacci récentes")
recent_alerts = st.session_state.get("fib_new_alerts", [])
if recent_alerts:
    st.dataframe(pd.DataFrame(recent_alerts[::-1]), width="stretch", hide_index=True)
else:
    st.info("Aucune nouvelle alerte Fibonacci depuis l'ouverture du dashboard.")

st.markdown("#### 📚 Journal complet des alertes")
alert_history = load_alert_history()
if not alert_history.empty:
    st.caption(
        f"{len(alert_history)} alerte(s) enregistrée(s) dans le journal local. "
        "Les colonnes Résultat et Notes sont prévues pour ton analyse après coup."
    )
    st.dataframe(alert_history.iloc[::-1], width="stretch", hide_index=True)
    csv_data = alert_history.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="⬇️ Télécharger le journal Fibonacci (CSV / Excel)",
        data=csv_data,
        file_name=f"journal_fibonacci_{datetime.now(pytz.timezone('America/New_York')).strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True
    )
else:
    st.info("Le journal sera créé automatiquement à la première nouvelle alerte confirmée.")

