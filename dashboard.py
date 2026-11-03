
    
  

            else:

                st.write("Aucune structure détectée.")

        # ---------------------------------------------
        # GRAPHIQUE
        # ---------------------------------------------

        fig = create_chart(
            df,
            gaps,
            events,
            timeframe,
            show_ema,
            show_fvg,
            show_structure
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            key=f"chart_{pair}_{timeframe}"
        )

        st.markdown("---")

    except Exception as e:

        st.error(
            f"Erreur pour {label} ({timeframe}) : {e}"
        )


# =========================================================
# PROFITS / PERTES - 7 DERNIERS JOURS
# =========================================================

st.subheader("📅 Profits / Pertes - 7 derniers jours")

try:

    since = (
        datetime.now(pytz.UTC) - timedelta(days=7)
    ).isoformat()

    request = TransactionList(
        accountID=ACCOUNT_ID,
        params={"from": since}
    )

    client.request(request)

    transactions = request.response.get(
        "transactions", []
    )

    pnl = {}

    for transaction in transactions:

        if (
            transaction["type"] == "ORDER_FILL"
            and "pl" in transaction
        ):

            date = transaction["time"].split("T")[0]

            pnl[date] = (
                pnl.get(date, 0)
                + float(transaction["pl"])
            )

    if pnl:

        df_pnl = pd.DataFrame(
            sorted(pnl.items()),
            columns=["Date", "P&L"]
        )

        df_pnl["P&L"] = df_pnl["P&L"].round(2)

        df_pnl["Status"] = df_pnl["P&L"].apply(
            lambda x: "Gain" if x >= 0 else "Perte"
        )

        st.dataframe(
            df_pnl,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "Aucune transaction enregistrée "
            "dans les 7 derniers jours."
        )

except Exception as e:

    st.error(f"Erreur OANDA : {e}")


# =========================================================
# DERNIÈRE MISE À JOUR
# =========================================================

now = datetime.now(NY_TZ)

st.caption(
    f"Dernière mise à jour : "
    f"{now.strftime('%Y-%m-%d %H:%M:%S')} NY"
)

