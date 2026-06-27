import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

st.set_page_config(page_title="スロット勝率分析", layout="wide")
st.title("スロット勝率分析ツール")
st.caption("min-repo.com のデータを取得して、勝率の高い機種を抽出します")

with st.sidebar:
    st.header("設定")
    min_daisu = st.number_input("最小設置台数", min_value=1, value=3, step=1)
    min_winrate = st.number_input("最小勝率 (%)", min_value=1.0, max_value=100.0, value=50.0, step=1.0)
    st.markdown("---")
    st.markdown("**URLの貼り付け方**")
    st.markdown("min-repo.com の機種別ページのURLを1行に1つずつ貼ってください")

import re
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

def parse_minrepo_date(date_text, reference_date):
    """'6/26(金)' のような文字列を date オブジェクトに変換する"""
    m = re.search(r'(\d{1,2})/(\d{1,2})', date_text)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    year = reference_date.year
    # 月が基準日より先（例: 基準が6月なのに11月）なら昨年分
    if month > reference_date.month:
        year -= 1
    try:
        return date(year, month, day)
    except ValueError:
        return None

st.subheader("STEP 1: 一覧ページからURLを自動取得（任意）")
with st.expander("店舗の日付一覧ページからURLをまとめて取得する"):
    store_url = st.text_input(
        "店舗の日付一覧ページURL",
        placeholder="https://min-repo.com/store/xxxxx/"
    )
    period_months = st.radio(
        "取得期間",
        options=[1, 2, 3],
        format_func=lambda x: f"{x}ヶ月",
        horizontal=True
    )
    fetch_button = st.button("URLを取得")

    if fetch_button and store_url:
        try:
            headers_tmp = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resp = requests.get(store_url.strip(), headers=headers_tmp, timeout=10)
            resp.raise_for_status()
            soup_tmp = BeautifulSoup(resp.content, 'html.parser')

            # 日付テキスト付きでリンクを収集
            candidates = []
            for a in soup_tmp.select('td a[href]'):
                href = a['href']
                text = a.get_text(strip=True)
                if not (href.startswith('https://min-repo.com') or href.startswith('/')):
                    continue
                if href.startswith('/'):
                    href = 'https://min-repo.com' + href
                candidates.append((text, href))

            if not candidates:
                st.warning("URLが見つかりませんでした。ページの構造が異なる可能性があります。")
            else:
                today = date.today()
                # 最新日付を特定
                parsed = [(parse_minrepo_date(t, today), h) for t, h in candidates]
                parsed = [(d, h) for d, h in parsed if d is not None]

                if not parsed:
                    st.warning("日付を解析できませんでした。URLだけ全件表示します。")
                    st.code('\n'.join(h for _, h in candidates), language=None)
                else:
                    newest = max(d for d, _ in parsed)
                    cutoff = newest - relativedelta(months=period_months)
                    filtered_links = [h for d, h in parsed if d > cutoff]
                    # 重複除去・順序保持
                    filtered_links = list(dict.fromkeys(filtered_links))
                    st.success(f"{len(filtered_links)}件のURLを取得しました（最新: {newest} / {period_months}ヶ月分）")
                    st.code('\n'.join(filtered_links), language=None)
                    st.caption("上のテキストをコピーして STEP 2 に貼り付けてください")
        except Exception as e:
            st.error(f"取得失敗: {e}")

st.subheader("STEP 2: URLを入力して分析")
url_text = st.text_area(
    "URLを1行1つで入力（例: https://min-repo.com/3170932/）",
    height=200,
    placeholder="https://min-repo.com/3170932/\nhttps://min-repo.com/3150729/\nhttps://min-repo.com/3128230/"
)

run_button = st.button("分析実行", type="primary", use_container_width=True)

if run_button:
    urls = [u.strip() for u in url_text.strip().splitlines() if u.strip()]
    urls = list(dict.fromkeys(urls))  # 重複除去

    if not urls:
        st.warning("URLを入力してください")
        st.stop()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    all_data = []
    progress = st.progress(0, text="データ取得中...")
    log = st.empty()

    for i, url in enumerate(urls):
        log.info(f"取得中 ({i+1}/{len(urls)}): {url}")
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
        except Exception as e:
            st.warning(f"取得失敗: {url} ({e})")
            time.sleep(2)
            progress.progress((i + 1) / len(urls))
            continue

        soup = BeautifulSoup(response.content, 'html.parser')
        title_tag = soup.find('h1')
        label = title_tag.text.strip() if title_tag else url

        table = soup.select_one('table.kishu._2dai')
        if not table:
            st.warning(f"テーブルが見つかりません: {label}")
            time.sleep(2)
            progress.progress((i + 1) / len(urls))
            continue

        for row in table.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) < 5:
                continue
            kishu = cols[0].text.strip()
            avg_diff = cols[1].text.strip()
            win_rate_str = cols[3].text.strip()
            deritsu = cols[4].text.strip()
            try:
                win, total = map(int, win_rate_str.split('/'))
                win_percent = round((win / total) * 100, 1)
                daisu = total
            except ValueError:
                continue

            all_data.append({
                '日付': label,
                '機種名': kishu,
                '台数': daisu,
                '勝率': win_rate_str,
                '勝率(%)': win_percent,
                '平均差枚': avg_diff,
                '出玉率': deritsu,
            })

        progress.progress((i + 1) / len(urls))
        if i < len(urls) - 1:
            time.sleep(2)

    log.empty()
    progress.empty()

    if not all_data:
        st.error("データを取得できませんでした")
        st.stop()

    df = pd.DataFrame(all_data)
    filtered = df[(df['台数'] >= min_daisu) & (df['勝率(%)'] > min_winrate)].copy()
    filtered = filtered.sort_values(by=['日付', '勝率(%)'], ascending=[True, False])

    st.success(f"完了！ {len(urls)}日分 / {len(filtered)}件 該当")

    # --- 自動解説 ---
    st.markdown("---")
    st.subheader("自動解説")

    counts_all = filtered['機種名'].value_counts()
    repeat_all = counts_all[counts_all >= 2]
    total_dates = len(urls)

    lines = []

    if repeat_all.empty:
        lines.append(f"今回の{total_dates}日分のデータでは、複数回登場した機種はありませんでした。イベント日が少ないか、店舗の傾向が分散している可能性があります。")
    else:
        top_kishu = repeat_all.index[0]
        top_cnt = repeat_all.iloc[0]
        top_rows = filtered[filtered['機種名'] == top_kishu]
        top_avg = round(top_rows['勝率(%)'].mean(), 1)
        top_daisu = top_rows['台数'].iloc[0]

        lines.append(f"**{total_dates}日分**のデータを分析した結果、複数回登場した機種は **{len(repeat_all)}機種** でした。")
        lines.append("")

        # 皆勤賞
        kankin = [(k, c) for k, c in repeat_all.items() if c >= total_dates * 0.8]
        if kankin:
            names = "・".join(f"**{k}**（{c}/{total_dates}日）" for k, c in kankin)
            lines.append(f"**皆勤賞クラス：** {names}")
            lines.append("ほぼ毎日条件を満たしており、店舗の看板機種と考えられます。")
            lines.append("")

        # 最多登場
        lines.append(f"**最多登場：{top_kishu}**（{top_cnt}/{total_dates}日、設置{top_daisu}台、平均勝率{top_avg}%）")
        if top_daisu >= 20:
            lines.append(f"設置台数が{top_daisu}台と多いにもかかわらず平均勝率{top_avg}%は優秀です。どの台に座っても期待値がプラスになりやすいと言えます。")
        else:
            lines.append(f"設置台数は{top_daisu}台と少なめですが、出た日の勝率が高く、台を確保できれば有力な狙い目です。")
        lines.append("")

        # 高勝率機種（80%以上）
        high_rate = [(k, c) for k, c in repeat_all.items()
                     if round(filtered[filtered['機種名'] == k]['勝率(%)'].mean(), 1) >= 80.0]
        if high_rate:
            names = "・".join(f"**{k}**（平均{round(filtered[filtered['機種名']==k]['勝率(%)'].mean(),1)}%）" for k, c in high_rate)
            lines.append(f"**高勝率機種（平均80%以上）：** {names}")
            lines.append("登場した日は特に強く、積極的に狙う価値があります。ただし台数が少ない機種は競争率も高い点に注意が必要です。")
            lines.append("")

        # 総評
        avg_winrate_overall = round(filtered['勝率(%)'].mean(), 1)
        if avg_winrate_overall >= 70:
            lines.append(f"**総評：** 全体の平均勝率は{avg_winrate_overall}%と非常に高く、抽選を突破できれば何に座っても期待値プラスになりやすい優良店舗です。")
        elif avg_winrate_overall >= 60:
            lines.append(f"**総評：** 全体の平均勝率は{avg_winrate_overall}%と高水準です。特定の機種に絞って狙うことで安定して勝率を高められます。")
        else:
            lines.append(f"**総評：** 全体の平均勝率は{avg_winrate_overall}%です。機種選択と日程選択の両方が重要な店舗です。複数回登場した機種を優先的に狙いましょう。")

    for line in lines:
        st.markdown(line)

    st.markdown("---")
    tab1, tab2 = st.tabs(["全日程一覧", "複数回登場まとめ"])

    with tab1:
        st.subheader(f"台数{min_daisu}台以上 & 勝率{min_winrate}%超 の機種")
        display_df = filtered[['日付', '機種名', '台数', '勝率', '勝率(%)', '平均差枚', '出玉率']].reset_index(drop=True)
        st.dataframe(display_df, use_container_width=True, height=600)
        st.download_button(
            label="CSVダウンロード（全日程一覧）",
            data=display_df.to_csv(index=False, encoding='utf-8-sig'),
            file_name="スロット分析_全日程.csv",
            mime="text/csv"
        )

    with tab2:
        st.subheader("複数回登場した機種（登場回数順）")
        counts = filtered['機種名'].value_counts()
        repeat = counts[counts >= 2]

        if repeat.empty:
            st.info("複数回登場した機種はありませんでした")
        else:
            summary_rows = []
            for kishu, cnt in repeat.items():
                rows = filtered[filtered['機種名'] == kishu]
                avg_win = round(rows['勝率(%)'].mean(), 1)
                dates = ', '.join(rows['日付'].tolist())
                daisu_list = '/'.join(str(d) for d in rows['台数'].tolist())
                summary_rows.append({
                    '機種名': kishu,
                    '登場回数': cnt,
                    '平均勝率(%)': avg_win,
                    '設置台数': daisu_list,
                    '日付': dates,
                })

            summary_df = pd.DataFrame(summary_rows)
            st.dataframe(summary_df, use_container_width=True, height=600)
            st.download_button(
                label="CSVダウンロード（複数回登場まとめ）",
                data=summary_df.to_csv(index=False, encoding='utf-8-sig'),
                file_name="スロット分析_複数回登場.csv",
                mime="text/csv"
            )
