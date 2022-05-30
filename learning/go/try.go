package main

import "fmt"

func findRepeatNumber(nums []int) int {
	dict := make(map[int]int)
	output := 0
	for i := 0; i < len(nums); i++ {
		_, ok := dict[nums[i]]
		dict[nums[i]] = 1
		if ok == true {
			output = nums[i]
			break
		}
	}
	return output
}

func main() {
	nums := []int{2, 3, 1, 0, 2, 5, 3}
	fmt.Println(findRepeatNumber(nums))
}
