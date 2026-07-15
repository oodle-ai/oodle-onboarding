class CreateVisits < ActiveRecord::Migration[7.1]
  def change
    create_table :visits do |t|
      t.string :path, null: false
      t.string :user_agent
      t.timestamps
    end
  end
end
