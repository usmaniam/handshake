"use client";
import Link from "next/link";
import { DealRow } from "@/lib/api";
import { day, money, when } from "@/lib/format";
import { dealAmount, dealItem, Tag, Track } from "./ui";

export default function DealRows({ deals }: { deals: DealRow[] }) {
  return (
    <ul className="rows">
      {deals.map((d) => (
        <li key={d.id}>
          <Link href={`/deals/${d.id}`} className="row deal">
            <div>
              <div className="title">{d.vendor ?? "Unknown vendor"}</div>
              <div className="sub">{dealItem(d)}</div>
            </div>
            <div className="sub">
              {d.accepted_terms ? `Due ${day(d.accepted_terms.deadline)}` : d.current_terms ? `Proposed ${when(d.created_at)}` : ""}
            </div>
            <div className="amt num">{money(dealAmount(d))}</div>
            <div><Tag state={d.state} /></div>
            <div className="track-cell" style={{ gridColumn: "1 / -1" }}><Track state={d.state} compact /></div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
