export default function RestrictedZone() {
  return (
    <g transform="translate(270 225)">
      <rect
        width="145"
        height="72"
        fill="#08090C"
        stroke="#F59E0B"
        strokeDasharray="4 2"
      />

      <rect
        width="145"
        height="72"
        fill="url(#hazard-pattern)"
        pointerEvents="none"
      />

      <rect
        x="8"
        y="8"
        width="129"
        height="20"
        fill="#08090C"
        stroke="#F59E0B"
        strokeWidth="0.8"
      />

      <text
        x="14"
        y="14"
        fill="#F59E0B"
        fontFamily="Inter, Arial, sans-serif"
        fontSize="7.5"
        fontWeight="700"
        dominantBaseline="hanging"
      >
        KHU VỰC HẠN CHẾ
      </text>
    </g>
  );
}


