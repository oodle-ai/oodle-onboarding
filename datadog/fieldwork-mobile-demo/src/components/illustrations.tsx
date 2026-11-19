import React from "react";
import Svg, { Circle, Path, Rect, Text } from "react-native-svg";

export function TruckArt() {
  return (
    <Svg
      width={166}
      height={116}
      viewBox="0 0 200 140"
      accessibilityElementsHidden
    >
      <Circle cx="103" cy="70" r="61" fill="#30634e" />
      <Path d="M15 113H188M30 124H164" stroke="#62856a" strokeWidth="2" />
      <Path d="M31 52H120L110 94H40Z" fill="#d4ef91" />
      <Path
        d="M44 58L50 87M62 58L67 87M80 58L84 87M98 58L101 87"
        stroke="#92b86e"
        strokeWidth="3"
      />
      <Path d="M117 70H150L172 88V106H111Z" fill="#f5f7ed" />
      <Path d="M130 76H147L160 88H130Z" fill="#2e6752" />
      <Path d="M30 98H174V107H30Z" fill="#9cba82" />
      <Circle cx="60" cy="108" r="13" fill="#153f32" />
      <Circle cx="60" cy="108" r="6" fill="#e4ebd4" />
      <Circle cx="149" cy="108" r="13" fill="#153f32" />
      <Circle cx="149" cy="108" r="6" fill="#e4ebd4" />
      <Path
        d="M157 38V22M149 30H165M34 33V23M29 28H39"
        stroke="#d4ef91"
        strokeWidth="2"
      />
    </Svg>
  );
}
export function RouteArt() {
  return (
    <Svg
      width="100%"
      height={145}
      viewBox="0 0 340 145"
      accessibilityLabel="Illustrated route overview. Use the stop list for actual locations."
    >
      <Rect width="340" height="145" fill="#e9eedf" rx="15" />
      <Path
        d="M0 40H340M0 90H340M65 0V145M160 0V145M265 0V145"
        stroke="#fafbf6"
        strokeWidth="14"
      />
      <Path d="M0 128L340 12" stroke="#c9dcd4" strokeWidth="22" />
      <Path
        d="M40 113L65 113L65 40L160 40L160 90L266 90L266 34"
        fill="none"
        stroke="#51836b"
        strokeWidth="4"
        strokeDasharray="6 4"
      />
      <Circle
        cx="65"
        cy="40"
        r="14"
        fill="#205b46"
        stroke="white"
        strokeWidth="3"
      />
      <Text
        x="65"
        y="44"
        fill="white"
        fontSize="11"
        textAnchor="middle"
        fontWeight="bold"
      >
        1
      </Text>
      <Circle
        cx="160"
        cy="90"
        r="14"
        fill="#205b46"
        stroke="white"
        strokeWidth="3"
      />
      <Text
        x="160"
        y="94"
        fill="white"
        fontSize="11"
        textAnchor="middle"
        fontWeight="bold"
      >
        2
      </Text>
      <Circle
        cx="266"
        cy="34"
        r="14"
        fill="#205b46"
        stroke="white"
        strokeWidth="3"
      />
      <Text
        x="266"
        y="38"
        fill="white"
        fontSize="11"
        textAnchor="middle"
        fontWeight="bold"
      >
        3
      </Text>
      <Circle
        cx="40"
        cy="113"
        r="7"
        fill="#cfeb93"
        stroke="#205b46"
        strokeWidth="3"
      />
    </Svg>
  );
}
